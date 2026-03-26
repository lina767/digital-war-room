"""
PDF Ingest Service — Download, extract text, chunk, embed, and store PDF documents.

Designed for OFAC SDN reports, UN Security Council resolutions, and similar
geopolitical reference PDFs. Chunks are stored in pgvector (if available)
and kept in an in-memory index for fast Document QA lookups.

Uses reportlab is already in requirements (for PDF export); text extraction
uses PyPDF2/pypdf or pdfplumber. Falls back to raw text if neither available.
"""

import hashlib
import io
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

PDF_CHUNK_SIZE = int(os.getenv("PDF_CHUNK_SIZE", "800"))
PDF_CHUNK_OVERLAP = int(os.getenv("PDF_CHUNK_OVERLAP", "100"))
PDF_MAX_PAGES = int(os.getenv("PDF_MAX_PAGES", "200"))
PDF_DOWNLOAD_TIMEOUT = int(os.getenv("PDF_DOWNLOAD_TIMEOUT", "60"))

# In-memory document store: doc_id → {metadata, chunks, embeddings}
_documents: Dict[str, Dict[str, Any]] = {}


def _doc_id(url_or_path: str) -> str:
    return hashlib.sha256(url_or_path.strip().encode()).hexdigest()[:16]


async def download_pdf(url: str) -> Optional[bytes]:
    """Download a PDF from a URL. Returns raw bytes or None."""
    try:
        async with httpx.AsyncClient(timeout=PDF_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.content) > 100:
                content_type = resp.headers.get("content-type", "")
                if "pdf" in content_type or resp.content[:5] == b"%PDF-":
                    return resp.content
                logger.warning("[pdf] URL %s returned non-PDF content-type: %s", url, content_type)
            else:
                logger.warning("[pdf] Failed to download %s: status %d", url, resp.status_code)
    except Exception as e:
        logger.error("[pdf] Download error for %s: %s", url, e)
    return None


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes. Tries pypdf first, then pdfplumber."""
    text = _extract_with_pypdf(pdf_bytes)
    if text and len(text.strip()) > 50:
        return text
    text = _extract_with_pdfplumber(pdf_bytes)
    if text and len(text.strip()) > 50:
        return text
    return ""


def _extract_with_pypdf(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for i, page in enumerate(reader.pages):
            if i >= PDF_MAX_PAGES:
                break
            t = page.extract_text()
            if t:
                pages.append(t)
        return "\n\n".join(pages)
    except ImportError:
        pass
    except Exception as e:
        logger.debug("[pdf] pypdf extraction failed: %s", e)
    return ""


def _extract_with_pdfplumber(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber

        pages = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                if i >= PDF_MAX_PAGES:
                    break
                t = page.extract_text()
                if t:
                    pages.append(t)
        return "\n\n".join(pages)
    except ImportError:
        pass
    except Exception as e:
        logger.debug("[pdf] pdfplumber extraction failed: %s", e)
    return ""


def chunk_text(text: str, chunk_size: int = 0, overlap: int = 0) -> List[str]:
    """Split text into overlapping chunks by character count, respecting sentence boundaries."""
    cs = chunk_size or PDF_CHUNK_SIZE
    ov = overlap or PDF_CHUNK_OVERLAP

    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(text) <= cs:
        return [text] if text else []

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sent in sentences:
        if current_len + len(sent) > cs and current:
            chunks.append(" ".join(current))
            overlap_text = " ".join(current)
            overlap_words = overlap_text[-ov:] if len(overlap_text) > ov else overlap_text
            current = [overlap_words, sent] if ov > 0 else [sent]
            current_len = sum(len(s) for s in current)
        else:
            current.append(sent)
            current_len += len(sent)

    if current:
        chunks.append(" ".join(current))

    return chunks


async def ingest_pdf(
    url: str,
    source: str = "pdf",
    conflict: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Full pipeline: download → extract → chunk → embed → store.
    Returns {"doc_id", "url", "chunk_count", "char_count"} or None.
    """
    doc_id = _doc_id(url)

    if doc_id in _documents:
        cached = _documents[doc_id]
        age = time.time() - cached.get("ingested_at", 0)
        if age < 24 * 3600:
            logger.debug("[pdf] Document %s already ingested (age %.0fh)", doc_id, age / 3600)
            return {
                "doc_id": doc_id,
                "url": url,
                "chunk_count": len(cached.get("chunks", [])),
                "char_count": cached.get("char_count", 0),
                "cached": True,
            }

    pdf_bytes = await download_pdf(url)
    if not pdf_bytes:
        return None

    text = extract_text_from_pdf(pdf_bytes)
    if not text:
        logger.warning("[pdf] No text extracted from %s", url)
        return None

    chunks = chunk_text(text)
    if not chunks:
        return None

    embeddings = None
    try:
        from services.hf_service import embed

        embeddings = await embed(chunks)
    except Exception as e:
        logger.debug("[pdf] Embedding failed: %s", e)

    if embeddings:
        try:
            from services.storage_service import is_available, store_embeddings_batch

            if is_available():
                items = [{"text": c} for c in chunks]
                await store_embeddings_batch(
                    items,
                    embeddings,
                    source=f"pdf:{source}",
                    conflict=conflict,
                )
        except Exception as e:
            logger.debug("[pdf] pgvector storage skipped: %s", e)

    _documents[doc_id] = {
        "url": url,
        "source": source,
        "conflict": conflict,
        "chunks": chunks,
        "embeddings": embeddings,
        "metadata": metadata or {},
        "char_count": len(text),
        "ingested_at": time.time(),
    }

    logger.info("[pdf] Ingested %s: %d chunks, %d chars", url, len(chunks), len(text))
    return {
        "doc_id": doc_id,
        "url": url,
        "chunk_count": len(chunks),
        "char_count": len(text),
        "cached": False,
    }


def get_chunks(doc_id: str) -> List[str]:
    """Return stored chunks for a document."""
    doc = _documents.get(doc_id)
    return doc["chunks"] if doc else []


def get_all_chunks_for_source(source: str) -> List[Tuple[str, str]]:
    """Return (doc_id, chunk_text) for all documents matching a source prefix."""
    results = []
    for doc_id, doc in _documents.items():
        doc_source = doc.get("source", "")
        if doc_source == source or doc_source.startswith(f"pdf:{source}"):
            for chunk in doc.get("chunks", []):
                results.append((doc_id, chunk))
    return results


async def find_relevant_chunks(
    question: str,
    source: Optional[str] = None,
    conflict: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Semantic search over ingested PDF chunks: embed the question,
    find nearest chunks via in-memory cosine sim (or pgvector if available).
    """
    try:
        from services.hf_service import _cosine_similarity, embed
    except ImportError:
        return []

    q_emb = await embed([question])
    if not q_emb or not q_emb[0]:
        return []
    q_vec = q_emb[0]

    try:
        from services.storage_service import find_similar, is_available

        if is_available():
            results = await find_similar(
                q_vec,
                top_k=top_k,
                source=f"pdf:{source}" if source else None,
                conflict=conflict,
                threshold=0.5,
            )
            if results:
                return results
    except Exception:
        pass

    # Fallback: in-memory search
    scored: List[Tuple[float, str, str]] = []
    for doc_id, doc in _documents.items():
        if source and not doc.get("source", "").endswith(source):
            continue
        if conflict and doc.get("conflict") != conflict:
            continue
        doc_embeddings = doc.get("embeddings")
        if not doc_embeddings:
            continue
        for _i, (chunk, emb) in enumerate(zip(doc.get("chunks", []), doc_embeddings, strict=True)):
            sim = _cosine_similarity(q_vec, emb)
            if sim >= 0.5:
                scored.append((sim, doc_id, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"similarity": s, "doc_id": did, "text_preview": c[:200], "text": c, "source": "in_memory"}
        for s, did, c in scored[:top_k]
    ]


def list_documents() -> List[Dict[str, Any]]:
    """List all ingested documents."""
    return [
        {
            "doc_id": doc_id,
            "url": doc.get("url", ""),
            "source": doc.get("source", ""),
            "conflict": doc.get("conflict", ""),
            "chunk_count": len(doc.get("chunks", [])),
            "char_count": doc.get("char_count", 0),
            "ingested_at": doc.get("ingested_at", 0),
        }
        for doc_id, doc in _documents.items()
    ]


def purge_in_memory_documents(max_age_hours: int) -> int:
    """Remove cached in-memory document payloads older than max_age_hours."""
    hours = max(1, int(max_age_hours))
    cutoff = time.time() - (hours * 3600)
    to_delete: list[str] = []
    for doc_id, doc in _documents.items():
        ingested_at = float(doc.get("ingested_at") or 0)
        if ingested_at and ingested_at < cutoff:
            to_delete.append(doc_id)
    for doc_id in to_delete:
        _documents.pop(doc_id, None)
    return len(to_delete)


# Well-known document URLs for auto-ingest
OFAC_SDN_PDF_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDNLIST.PDF"
UN_SC_IRAN_RESOLUTIONS = [
    "https://undocs.org/pdf?symbol=S/RES/2231(2015)",
]
