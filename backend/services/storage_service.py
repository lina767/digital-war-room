"""
Storage Service — pgvector-backed vector storage for embeddings.

Provides persistent embedding storage and database-level similarity queries
using PostgreSQL + pgvector. Falls back gracefully to in-memory operations
(via hf_service) when DATABASE_URL is not configured.

Requires: asyncpg, pgvector extension on PostgreSQL.
Migration: backend/migrations/001_pgvector_setup.sql, 003_multi_tenancy.sql
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
_pool = None


def _tid(tenant_id: Optional[uuid.UUID]) -> uuid.UUID:
    if tenant_id is not None:
        return tenant_id
    try:
        from services.request_context import get_current_tenant_id

        return get_current_tenant_id()
    except Exception:
        from services.tenant_constants import get_default_tenant_id

        return get_default_tenant_id()


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
    tenant_id: Optional[uuid.UUID] = None,
) -> bool:
    """
    Store an embedding in the database. Uses content_hash for upsert.
    Returns True on success, False on failure or no DB.
    """
    pool = await _get_pool()
    if not pool:
        return False

    tid = _tid(tenant_id)
    content_hash = _content_hash(text)
    preview = text[:200] if text else ""
    meta = metadata or {}

    try:
        async with pool.acquire() as conn:
            from services.db_tenant import set_session_tenant

            await set_session_tenant(conn, tid, None)
            await conn.execute(
                """
                INSERT INTO embeddings (tenant_id, content_hash, source, text_preview, embedding, metadata, conflict)
                VALUES ($1, $2, $3, $4, $5::vector, $6, $7)
                ON CONFLICT (tenant_id, content_hash) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                tid,
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
    tenant_id: Optional[uuid.UUID] = None,
) -> int:
    """
    Batch-store embeddings. Each item should have a 'text' key.
    Returns count of successfully stored items.
    """
    pool = await _get_pool()
    if not pool:
        return 0

    tid = _tid(tenant_id)
    stored = 0
    try:
        async with pool.acquire() as conn:
            from services.db_tenant import set_session_tenant

            await set_session_tenant(conn, tid, None)
            for item, emb in zip(items, embeddings, strict=True):
                text = item.get("text") or item.get("title") or item.get("summary") or ""
                if not text or not emb:
                    continue
                content_hash = _content_hash(text)
                preview = text[:200]
                try:
                    await conn.execute(
                        """
                        INSERT INTO embeddings (tenant_id, content_hash, source, text_preview, embedding, metadata, conflict)
                        VALUES ($1, $2, $3, $4, $5::vector, $6, $7)
                        ON CONFLICT (tenant_id, content_hash) DO UPDATE SET
                            embedding = EXCLUDED.embedding,
                            updated_at = now()
                        """,
                        tid,
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
    tenant_id: Optional[uuid.UUID] = None,
) -> List[Dict[str, Any]]:
    """
    Find similar items by cosine similarity using pgvector.
    Returns [{"content_hash", "text_preview", "source", "similarity", "metadata"}].
    """
    pool = await _get_pool()
    if not pool:
        return []

    tid = _tid(tenant_id)
    try:
        conditions = ["tenant_id = $2", "1 - (embedding <=> $1::vector) >= $3"]
        params: list = [str(embedding), tid, threshold]
        idx = 4

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
            from services.db_tenant import set_session_tenant

            await set_session_tenant(conn, tid, None)
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


async def count_recent_embeddings(
    *,
    source: str,
    conflict: Optional[str] = None,
    max_age_hours: int = 72,
    decision: Optional[str] = None,
    tenant_id: Optional[uuid.UUID] = None,
) -> int:
    """
    Count embeddings for a source within a time window.
    Optional filters:
    - conflict
    - decision: matches metadata->>'decision'
    """
    pool = await _get_pool()
    if not pool:
        return 0

    tid = _tid(tenant_id)
    max_age_hours = max(1, int(max_age_hours))
    decision = decision.strip().lower() if isinstance(decision, str) and decision.strip() else None
    try:
        conditions = [
            "tenant_id = $1",
            "source = $2",
            "updated_at >= NOW() - ($3::text || ' hours')::interval",
        ]
        params: list = [tid, source, str(max_age_hours)]
        idx = 4

        if conflict:
            conditions.append(f"conflict = ${idx}")
            params.append(conflict)
            idx += 1
        if decision:
            conditions.append(f"(metadata->>'decision') = ${idx}")
            params.append(decision)
            idx += 1

        where = " AND ".join(conditions)
        query = f"SELECT COUNT(*) AS n FROM embeddings WHERE {where}"
        async with pool.acquire() as conn:
            from services.db_tenant import set_session_tenant

            await set_session_tenant(conn, tid, None)
            row = await conn.fetchrow(query, *params)
            return int(row["n"]) if row and "n" in row else 0
    except Exception as e:
        logger.error("[storage] count_recent_embeddings failed: %s", e)
        return 0


async def deduplicate_by_db(
    texts: List[str],
    source: str = "unknown",
    threshold: float = 0.92,
    tenant_id: Optional[uuid.UUID] = None,
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

    tid = _tid(tenant_id)
    novel_indices = []
    for i, (text, emb) in enumerate(zip(texts, embeddings, strict=True)):
        similar = await find_similar(emb, top_k=1, source=source, threshold=threshold, tenant_id=tid)
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


async def prune_old_embeddings(days: int) -> int:
    """Best-effort retention cleanup for embeddings by updated_at."""
    pool = await _get_pool()
    if not pool:
        return 0
    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM embeddings
                WHERE updated_at < NOW() - ($1::text || ' days')::interval
                """,
                max(1, int(days)),
            )
        return int((result or "DELETE 0").split()[-1])
    except Exception as e:
        logger.warning("[storage] prune_old_embeddings failed: %s", e)
        return 0
