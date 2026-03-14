"""
Storage Service — pgvector-backed vector storage for embeddings.

Provides persistent embedding storage and database-level similarity queries
using PostgreSQL + pgvector. Falls back gracefully to in-memory operations
(via hf_service) when DATABASE_URL is not configured.

Requires: asyncpg, pgvector extension on PostgreSQL.
Migration: backend/migrations/001_pgvector_setup.sql
"""
import hashlib
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
_pool = None


async def _get_pool():
    """Lazy-initialize the asyncpg connection pool."""
    global _pool
    if _pool is not None:
        return _pool
    if not DATABASE_URL:
        return None
    try:
        import asyncpg
        from pgvector.asyncpg import register_vector

        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        async with _pool.acquire() as conn:
            await register_vector(conn)
        logger.info("[storage] pgvector pool initialized")
        return _pool
    except Exception as e:
        logger.warning("[storage] Failed to init pgvector pool: %s", e)
        _pool = None
        return None


def is_available() -> bool:
    """Quick check: is DATABASE_URL configured?"""
    return bool(DATABASE_URL)


def _content_hash(text: str) -> str:
    """Deterministic hash for dedup lookups."""
    return hashlib.sha256(text.strip()[:500].encode()).hexdigest()


async def store_embedding(
    text: str,
    embedding: List[float],
    source: str = "unknown",
    conflict: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Store an embedding in the database. Uses content_hash for upsert.
    Returns True on success, False on failure or no DB.
    """
    pool = await _get_pool()
    if not pool:
        return False

    content_hash = _content_hash(text)
    preview = text[:200] if text else ""
    meta = metadata or {}

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO embeddings (content_hash, source, text_preview, embedding, metadata, conflict)
                VALUES ($1, $2, $3, $4::vector, $5, $6)
                ON CONFLICT (content_hash) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                content_hash,
                source,
                preview,
                str(embedding),
                meta,
                conflict or None,
            )
        return True
    except Exception as e:
        logger.error("[storage] store_embedding failed: %s", e)
        return False


async def store_embeddings_batch(
    items: List[Dict[str, Any]],
    embeddings: List[List[float]],
    source: str = "unknown",
    conflict: str = "",
) -> int:
    """
    Batch-store embeddings. Each item should have a 'text' key.
    Returns count of successfully stored items.
    """
    pool = await _get_pool()
    if not pool:
        return 0

    stored = 0
    try:
        async with pool.acquire() as conn:
            for item, emb in zip(items, embeddings):
                text = item.get("text") or item.get("title") or item.get("summary") or ""
                if not text or not emb:
                    continue
                content_hash = _content_hash(text)
                preview = text[:200]
                try:
                    await conn.execute(
                        """
                        INSERT INTO embeddings (content_hash, source, text_preview, embedding, metadata, conflict)
                        VALUES ($1, $2, $3, $4::vector, $5, $6)
                        ON CONFLICT (content_hash) DO UPDATE SET
                            embedding = EXCLUDED.embedding,
                            updated_at = now()
                        """,
                        content_hash,
                        source,
                        preview,
                        str(emb),
                        {},
                        conflict or None,
                    )
                    stored += 1
                except Exception:
                    continue
    except Exception as e:
        logger.error("[storage] store_embeddings_batch failed: %s", e)

    if stored:
        logger.info("[storage] Stored %d/%d embeddings (source=%s)", stored, len(items), source)
    return stored


async def find_similar(
    embedding: List[float],
    top_k: int = 10,
    source: Optional[str] = None,
    conflict: Optional[str] = None,
    threshold: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    Find similar items by cosine similarity using pgvector.
    Returns [{"content_hash", "text_preview", "source", "similarity", "metadata"}].
    """
    pool = await _get_pool()
    if not pool:
        return []

    try:
        conditions = ["1 - (embedding <=> $1::vector) >= $2"]
        params: list = [str(embedding), threshold]
        idx = 3

        if source:
            conditions.append(f"source = ${idx}")
            params.append(source)
            idx += 1
        if conflict:
            conditions.append(f"conflict = ${idx}")
            params.append(conflict)
            idx += 1

        where = " AND ".join(conditions)
        query = f"""
            SELECT content_hash, text_preview, source, metadata,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM embeddings
            WHERE {where}
            ORDER BY embedding <=> $1::vector
            LIMIT {top_k}
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [
                {
                    "content_hash": r["content_hash"],
                    "text_preview": r["text_preview"],
                    "source": r["source"],
                    "similarity": float(r["similarity"]),
                    "metadata": r["metadata"] or {},
                }
                for r in rows
            ]
    except Exception as e:
        logger.error("[storage] find_similar failed: %s", e)
        return []


async def deduplicate_by_db(
    texts: List[str],
    source: str = "unknown",
    threshold: float = 0.92,
) -> List[int]:
    """
    Check texts against stored embeddings to find near-duplicates.
    Returns list of indices that are NOT duplicates (i.e., novel items).
    Falls back to returning all indices if DB is unavailable.
    """
    pool = await _get_pool()
    if not pool:
        return list(range(len(texts)))

    try:
        from services.hf_service import embed
    except ImportError:
        return list(range(len(texts)))

    embeddings = await embed(texts)
    if not embeddings:
        return list(range(len(texts)))

    novel_indices = []
    for i, (text, emb) in enumerate(zip(texts, embeddings)):
        similar = await find_similar(emb, top_k=1, source=source, threshold=threshold)
        if not similar:
            novel_indices.append(i)
        else:
            existing_hash = similar[0]["content_hash"]
            current_hash = _content_hash(text)
            if existing_hash == current_hash:
                novel_indices.append(i)

    return novel_indices


async def close():
    """Close the connection pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("[storage] pgvector pool closed")
