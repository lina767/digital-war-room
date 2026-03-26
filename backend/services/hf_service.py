"""
Hugging Face Service — Central wrapper for HF Inference API calls.

Handles: embeddings, semantic deduplication, cross-encoder ranking.
Later phases add: NER bulk, document QA, OCR, CLIP, object detection, Whisper.

Features:
- In-memory cache with per-task TTL and LRU eviction
- Pure-Python cosine similarity (no numpy dependency)
- Warmup function for cold-start mitigation
- Graceful degradation (errors → None / empty list)
"""

import hashlib
import logging
import math
import os
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")
# Serverless Inference API host (no trailing path). Pipeline routes disambiguate tasks; see _hf_post_pipeline.
HF_INFERENCE_API = os.getenv("HF_INFERENCE_API", "https://api-inference.huggingface.co").rstrip("/")
# Legacy: full URL prefix ending before the model id, e.g. https://router.huggingface.co/hf-inference/models
# If set, NER/QA still POST to {HF_API_BASE}/{model}. Prefer HF_INFERENCE_API for new deployments.
HF_API_BASE = os.getenv("HF_API_BASE", "").rstrip("/")
HF_API_TIMEOUT = int(os.getenv("HF_API_TIMEOUT", "45"))
HF_CACHE_MAX_SIZE = int(os.getenv("HF_CACHE_MAX_SIZE", "10000"))

# Models
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
NER_BULK_MODEL = "Davlan/bert-base-multilingual-cased-ner-hrl"
DOC_QA_MODEL = os.getenv("HF_DOC_QA_MODEL", "deepset/roberta-base-squad2")

# Per-task cache TTL (seconds)
CACHE_TTL = {
    "embed": 7 * 24 * 3600,
    "cross_encode": 7 * 24 * 3600,
    "ner_bulk": 3 * 24 * 3600,
    "doc_qa": 6 * 3600,
}

# ── Cache ────────────────────────────────────────────────────────────────────

_cache: OrderedDict[str, Tuple[float, Any]] = OrderedDict()


def _cache_key(prefix: str, data: str) -> str:
    truncated = data[:500]
    h = hashlib.md5((truncated + prefix).encode(), usedforsecurity=False).hexdigest()
    return f"{prefix}:{h}"


def _cache_get(key: str) -> Any:
    if key in _cache:
        ts, val = _cache[key]
        ttl_key = key.split(":")[0]
        ttl = CACHE_TTL.get(ttl_key, 3600)
        if time.time() - ts < ttl:
            _cache.move_to_end(key)
            return val
        del _cache[key]
    return None


def _cache_set(key: str, val: Any):
    _cache[key] = (time.time(), val)
    _cache.move_to_end(key)
    while len(_cache) > HF_CACHE_MAX_SIZE:
        _cache.popitem(last=False)


# ── HTTP client ──────────────────────────────────────────────────────────────


def _headers() -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if HUGGINGFACE_API_KEY:
        h["Authorization"] = f"Bearer {HUGGINGFACE_API_KEY}"
    return h


def _models_url(model: str) -> str:
    """URL for /models/{model} inference (token classification, QA, etc.)."""
    if HF_API_BASE:
        return f"{HF_API_BASE}/{model}"
    return f"{HF_INFERENCE_API}/models/{model}"


def _pipeline_url(task: str, model: str) -> str:
    """URL for /pipeline/{task}/{model} (feature-extraction, text-classification, …)."""
    return f"{HF_INFERENCE_API}/pipeline/{task}/{model}"


async def _hf_post_url(url: str, payload: Dict[str, Any], timeout: int = 0, log_name: str = "") -> Any:
    """POST to a full HF Inference API URL. Returns parsed JSON or None on failure."""
    t = timeout or HF_API_TIMEOUT
    label = log_name or url.split("/")[-1]
    try:
        async with httpx.AsyncClient(timeout=t) as client:
            resp = await client.post(url, json=payload, headers=_headers())
            if resp.status_code == 503:
                wait = 30
                try:
                    body = resp.json()
                    wait = min(int(body.get("estimated_time", 30)), 60)
                except Exception:
                    pass
                logger.info("[hf] Model %s loading, waiting %ds...", label, wait)
                import asyncio

                await asyncio.sleep(wait)
                resp = await client.post(url, json=payload, headers=_headers())
            if resp.status_code != 200:
                logger.warning("[hf] %s returned %d: %s", label, resp.status_code, resp.text[:200])
                return None
            return resp.json()
    except Exception as e:
        logger.error("[hf] Request to %s failed: %s", label, e)
        return None


async def _hf_post_models(model: str, payload: Dict[str, Any], timeout: int = 0) -> Any:
    return await _hf_post_url(_models_url(model), payload, timeout=timeout, log_name=model)


async def _hf_post_pipeline(task: str, model: str, payload: Dict[str, Any], timeout: int = 0) -> Any:
    return await _hf_post_url(_pipeline_url(task, model), payload, timeout=timeout, log_name=f"{task}/{model}")


# ── Pure-Python cosine similarity ────────────────────────────────────────────


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _cross_encoder_relevance_score(item: Any) -> float:
    """
    Turn one hf-inference text-classification result element into a scalar relevance score.
    Cross-encoder Marco models usually return two labels; we use LABEL_1 / *1 as the relevant class.
    """
    if isinstance(item, (int, float)):
        return float(item)
    if isinstance(item, dict):
        return float(item.get("score", 0))
    if isinstance(item, list) and item:
        if all(isinstance(x, dict) for x in item):
            for d in item:
                lab = str(d.get("label", ""))
                if lab == "LABEL_1" or lab.endswith("1"):
                    return float(d.get("score", 0))
            return float(item[-1].get("score", 0))
        if isinstance(item[0], (int, float)):
            return float(item[0])
    return 0.0


# ── Embeddings ───────────────────────────────────────────────────────────────


async def embed(texts: List[str]) -> Optional[List[List[float]]]:
    """
    Generate embeddings via sentence-transformers/all-MiniLM-L6-v2 (384 dim).
    Batch-capable: up to 16 texts per request.
    Returns list of vectors or None on failure.
    """
    if not texts:
        return []
    if not HUGGINGFACE_API_KEY:
        logger.debug("[hf] No HUGGINGFACE_API_KEY, skipping embed")
        return None

    all_embeddings: List[Optional[List[float]]] = [None] * len(texts)
    uncached_indices: List[int] = []
    uncached_texts: List[str] = []

    for i, t in enumerate(texts):
        key = _cache_key("embed", t)
        cached = _cache_get(key)
        if cached is not None:
            all_embeddings[i] = cached
        else:
            uncached_indices.append(i)
            uncached_texts.append(t)

    if uncached_texts:
        batch_size = 16
        for start in range(0, len(uncached_texts), batch_size):
            batch = uncached_texts[start : start + batch_size]
            result = await _hf_post_pipeline(
                "feature-extraction",
                EMBED_MODEL,
                {"inputs": batch, "options": {"wait_for_model": True}},
            )
            if result and isinstance(result, list):
                if len(result) == len(batch):
                    for j, vec in enumerate(result):
                        idx = uncached_indices[start + j]
                        if not isinstance(vec, list):
                            logger.warning("[hf] Embedding batch unexpected element shape")
                            return None
                        try:
                            row = [float(x) for x in vec]
                        except (TypeError, ValueError):
                            logger.warning("[hf] Embedding batch unexpected element shape")
                            return None
                        all_embeddings[idx] = row
                        _cache_set(_cache_key("embed", batch[j]), row)
                elif len(batch) == 1 and result and isinstance(result[0], (int, float)):
                    # Some API versions return a single flat vector for one input string
                    row = [float(x) for x in result]
                    idx = uncached_indices[start]
                    all_embeddings[idx] = row
                    _cache_set(_cache_key("embed", batch[0]), row)
                else:
                    logger.warning("[hf] Embedding batch failed or unexpected shape")
                    return None
            else:
                logger.warning("[hf] Embedding batch failed or unexpected shape")
                return None

    if any(e is None for e in all_embeddings):
        return None
    return all_embeddings  # type: ignore[return-value]


# ── Semantic deduplication ───────────────────────────────────────────────────


async def deduplicate_items(
    items: List[Dict[str, Any]],
    text_key: str = "title",
    threshold: float = 0.92,
    source: str = "unknown",
    conflict: str = "",
    persist: bool = True,
) -> List[Dict[str, Any]]:
    """
    Semantic deduplication: embed all items, group by cosine similarity,
    keep the item with the highest sentiment_score from each group.
    Falls back to returning items unchanged if HF is unavailable.
    When persist=True and DATABASE_URL is set, stores surviving embeddings in pgvector.
    """
    if len(items) <= 1:
        return items

    texts = []
    for item in items:
        t = item.get(text_key) or item.get("title") or item.get("text") or ""
        summary = item.get("summary") or item.get("body_excerpt") or ""
        texts.append(f"{t} {summary}".strip()[:300])

    embeddings = await embed(texts)
    if not embeddings:
        return items

    n = len(items)
    is_duplicate = [False] * n

    for i in range(n):
        if is_duplicate[i]:
            continue
        for j in range(i + 1, n):
            if is_duplicate[j]:
                continue
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim >= threshold:
                score_i = items[i].get("sentiment_score") or 0
                score_j = items[j].get("sentiment_score") or 0
                if abs(score_j) > abs(score_i):
                    is_duplicate[i] = True
                    break
                else:
                    is_duplicate[j] = True

    result = [item for item, dup in zip(items, is_duplicate, strict=True) if not dup]
    result_embeddings = [emb for emb, dup in zip(embeddings, is_duplicate, strict=True) if not dup]

    if len(result) < len(items):
        logger.info("[hf] Dedup: %d → %d items (threshold %.2f)", len(items), len(result), threshold)

    if persist and result_embeddings:
        await _persist_embeddings(result, result_embeddings, source, conflict)

    return result


async def _persist_embeddings(
    items: List[Dict[str, Any]],
    embeddings: List[List[float]],
    source: str,
    conflict: str,
):
    """Store embeddings in pgvector if available. Graceful no-op otherwise."""
    try:
        from services.storage_service import is_available, store_embeddings_batch

        if not is_available():
            return
        text_items = [{"text": (it.get("title") or it.get("text") or it.get("summary") or "")[:300]} for it in items]
        await store_embeddings_batch(text_items, embeddings, source=source, conflict=conflict)
    except Exception as e:
        logger.debug("[hf] Embedding persistence skipped: %s", e)


# ── Cross-encoder ranking ────────────────────────────────────────────────────

# Ranking queries per conflict (configurable via env, e.g. RANKING_QUERY_IRAN)
_RANKING_QUERIES: Dict[str, str] = {
    "iran": os.getenv(
        "RANKING_QUERY_IRAN",
        "Iran nuclear sanctions military IRGC",
    ),
    "ukraine": os.getenv(
        "RANKING_QUERY_UKRAINE",
        "Ukraine Russia military invasion NATO",
    ),
}


def _get_ranking_query(conflict: str) -> str:
    """Resolve the ranking query for a conflict. Falls back to the conflict string itself."""
    cl = conflict.lower().strip()
    for key, query in _RANKING_QUERIES.items():
        if key in cl:
            return query
    env_key = f"RANKING_QUERY_{conflict.upper().replace(' ', '_').replace('-', '_')}"
    return os.getenv(env_key, conflict)


async def rank_by_relevance(
    query: str,
    texts: List[str],
    top_k: int = 20,
) -> List[Tuple[int, float]]:
    """
    Cross-encoder ranking: score each (query, text) pair.
    Returns [(original_index, relevance_score)] sorted by score descending, up to top_k.
    Falls back to returning indices in original order if HF is unavailable.
    """
    if not texts:
        return []
    if not HUGGINGFACE_API_KEY:
        return [(i, 0.0) for i in range(min(top_k, len(texts)))]

    pairs = [[query, t[:512]] for t in texts]
    result = await _hf_post_pipeline(
        "text-classification",
        CROSS_ENCODER_MODEL,
        {"inputs": pairs, "options": {"wait_for_model": True}},
        timeout=max(HF_API_TIMEOUT, 60),
    )

    if result and isinstance(result, list) and len(result) == len(texts):
        scores = [_cross_encoder_relevance_score(item) for item in result]
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return indexed[:top_k]

    logger.warning("[hf] Cross-encoder ranking failed, returning original order")
    return [(i, 0.0) for i in range(min(top_k, len(texts)))]


# ── NER Bulk Fallback (Phase 2) ──────────────────────────────────────────────


async def ner_bulk(texts: List[str]) -> Optional[List[List[Dict[str, Any]]]]:
    """
    Multilingual NER via Davlan/bert-base-multilingual-cased-ner-hrl.
    Supports Farsi, Arabic, English and more. Less precise than Haiku NER
    but suitable for high-volume overflow processing.
    Returns [[{"entity_group", "word", "start", "end", "score"}]] or None.
    """
    if not texts:
        return []
    if not HUGGINGFACE_API_KEY:
        return None

    all_results: List[Optional[List[Dict[str, Any]]]] = [None] * len(texts)
    uncached_indices: List[int] = []
    uncached_texts: List[str] = []

    for i, t in enumerate(texts):
        key = _cache_key("ner_bulk", t)
        cached = _cache_get(key)
        if cached is not None:
            all_results[i] = cached
        else:
            uncached_indices.append(i)
            uncached_texts.append(t)

    for idx, text in zip(uncached_indices, uncached_texts, strict=True):
        result = await _hf_post_models(
            NER_BULK_MODEL,
            {"inputs": text[:512], "options": {"wait_for_model": True}},
        )
        if result and isinstance(result, list):
            entities = []
            for ent in result:
                if isinstance(ent, dict) and ent.get("word"):
                    entities.append(
                        {
                            "entity": ent.get("word", "").replace("##", ""),
                            "type": _normalize_ner_type(ent.get("entity_group", ent.get("entity", "MISC"))),
                            "score": float(ent.get("score", 0)),
                            "start": ent.get("start", 0),
                            "end": ent.get("end", 0),
                            "context": "",
                        }
                    )
            all_results[idx] = entities
            _cache_set(_cache_key("ner_bulk", text), entities)
        else:
            all_results[idx] = []

    return [r if r is not None else [] for r in all_results]


def _normalize_ner_type(raw_type: str) -> str:
    """Map HF NER entity types to the unified type system used by Haiku NER."""
    mapping = {
        "PER": "PERSON",
        "LOC": "LOCATION",
        "ORG": "ORG",
        "MISC": "MISC",
        "B-PER": "PERSON",
        "I-PER": "PERSON",
        "B-LOC": "LOCATION",
        "I-LOC": "LOCATION",
        "B-ORG": "ORG",
        "I-ORG": "ORG",
        "B-MISC": "MISC",
        "I-MISC": "MISC",
    }
    return mapping.get(raw_type.strip(), raw_type.strip().upper())


# ── Document QA (Phase 4) ────────────────────────────────────────────────────


async def document_qa(
    question: str,
    context: str,
) -> Optional[Dict[str, Any]]:
    """
    Extractive question answering over a text chunk using deepset/roberta-base-squad2.
    Returns {"answer": str, "score": float, "start": int, "end": int} or None.
    """
    if not question or not context:
        return None
    if not HUGGINGFACE_API_KEY:
        return None

    cache_key = _cache_key("doc_qa", f"{question}|{context[:200]}")
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    result = await _hf_post_models(
        DOC_QA_MODEL,
        {
            "inputs": {"question": question, "context": context[:2048]},
            "options": {"wait_for_model": True},
        },
    )
    if result and isinstance(result, dict) and result.get("answer"):
        parsed = {
            "answer": result["answer"],
            "score": float(result.get("score", 0)),
            "start": result.get("start", 0),
            "end": result.get("end", 0),
        }
        _cache_set(cache_key, parsed)
        return parsed
    return None


async def document_qa_multi(
    question: str,
    chunks: List[str],
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    Run extractive QA across multiple text chunks, return the best answers
    sorted by score descending (up to top_k).
    """
    if not chunks or not question:
        return []

    results = []
    for i, chunk in enumerate(chunks):
        answer = await document_qa(question, chunk)
        if answer and answer.get("answer"):
            results.append({**answer, "chunk_index": i})

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:top_k]


# ── Warmup ───────────────────────────────────────────────────────────────────


async def warmup():
    """
    Send lightweight dummy requests to warm up HF model endpoints.
    Call at the start of each 6h analysis run to avoid cold-start latency.
    """
    if not HUGGINGFACE_API_KEY:
        return
    logger.info("[hf] Warming up models...")
    await embed(["warmup"])
    await _hf_post_pipeline(
        "text-classification",
        CROSS_ENCODER_MODEL,
        {"inputs": [["warmup query", "warmup text"]], "options": {"wait_for_model": True}},
    )
    await _hf_post_models(
        NER_BULK_MODEL,
        {"inputs": "warmup text", "options": {"wait_for_model": True}},
    )
    await _hf_post_models(
        DOC_QA_MODEL,
        {"inputs": {"question": "warmup", "context": "warmup text"}, "options": {"wait_for_model": True}},
    )
    logger.info("[hf] Warmup complete")
