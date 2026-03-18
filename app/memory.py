"""
Memory tools for the Receipts Agent.

Provides persistent memory via SQLite: save insights, search memories,
log query snapshots, and recall history. Uses FTS5 for full-text search.

CHANGELOG:
- 2026-03-18: Initial memory tools implementation (STORY-074)

TODO:
- None
"""

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"insight", "user_context", "observation"}
VALID_TOPICS = {"spending", "prices", "products", "stores", "trends", "other"}
MAX_SNAPSHOT_BYTES = 4096


def sanitize_fts5_query(query: str) -> str:
    """Escape FTS5 special operators to prevent injection.

    Removes AND, OR, NOT, NEAR operators and special characters
    (quotes, parens, colons, asterisks, carets) from user input.

    Args:
        query: Raw user query string.

    Returns:
        Sanitized string safe for FTS5 MATCH.
    """
    # Remove FTS5 boolean operators (as whole words)
    sanitized = re.sub(r"\b(AND|OR|NOT|NEAR)\b", " ", query)
    # Remove special FTS5 characters
    sanitized = re.sub(r"[\"\'()*:^]", " ", sanitized)
    # Collapse whitespace
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized


def _content_hash(content: str) -> str:
    """Generate SHA-256 hash of normalized content for dedup.

    Args:
        content: Raw content string.

    Returns:
        Hex digest of SHA-256 hash.
    """
    normalized = content.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def save_insight(
    db: aiosqlite.Connection,
    user_id: str,
    content: str,
    category: str = "insight",
    max_memories: int = 200,
) -> dict:
    """Store or update a derived insight in the memories table.

    Deduplicates via content_hash (SHA-256 of normalized content).
    On duplicate, updates the content and updated_at (upsert pattern).
    Enforces max_memories capacity by evicting oldest when over limit.

    Args:
        db: Open aiosqlite connection.
        user_id: User identifier.
        content: The insight text to store.
        category: One of insight, user_context, observation.
        max_memories: Maximum memories to retain per user.

    Returns:
        Dict with status ('saved', 'updated', or 'error') and id.
    """
    if category not in VALID_CATEGORIES:
        return {"status": "error", "message": f"Invalid category: {category}"}

    content_h = _content_hash(content)
    now = datetime.now(timezone.utc).isoformat()
    memory_id = str(uuid.uuid4())

    try:
        await db.execute(
            """INSERT INTO memories (id, user_id, category, content, content_hash,
               confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 1.0, ?, ?)""",
            (memory_id, user_id, category, content, content_h, now, now),
        )
        action = "saved"
        result_id = memory_id
    except aiosqlite.IntegrityError:
        # Duplicate content_hash — update existing (upsert)
        await db.execute(
            """UPDATE memories SET content = ?, updated_at = ?
               WHERE user_id = ? AND category = ? AND content_hash = ?""",
            (content, now, user_id, category, content_h),
        )
        cursor = await db.execute(
            "SELECT id FROM memories WHERE user_id = ? AND category = ? AND content_hash = ?",
            (user_id, category, content_h),
        )
        row = await cursor.fetchone()
        result_id = row[0] if row else memory_id
        action = "updated"

    # Enforce capacity — evict oldest when over limit
    cursor = await db.execute(
        """SELECT COUNT(*) FROM memories
           WHERE user_id = ?
           AND (expires_at IS NULL OR expires_at > datetime('now'))""",
        (user_id,),
    )
    (count,) = await cursor.fetchone()
    if count > max_memories:
        excess = count - max_memories
        await db.execute(
            """DELETE FROM memories WHERE id IN (
               SELECT id FROM memories WHERE user_id = ?
               AND (expires_at IS NULL OR expires_at > datetime('now'))
               ORDER BY created_at ASC LIMIT ?)""",
            (user_id, excess),
        )

    await db.commit()
    logger.info("Memory %s %s for user %s", result_id, action, user_id)
    return {"status": action, "id": result_id}


async def search_memories(
    db: aiosqlite.Connection,
    user_id: str,
    query: str,
    limit: int = 5,
) -> list[dict]:
    """FTS5 search over stored memories.

    Sanitizes query input to escape special FTS5 operators.

    Args:
        db: Open aiosqlite connection.
        user_id: User identifier.
        query: Search query string.
        limit: Maximum results to return.

    Returns:
        List of matching memory dicts with content, category, created_at.
    """
    sanitized = sanitize_fts5_query(query)
    if not sanitized:
        return []

    try:
        cursor = await db.execute(
            """SELECT m.content, m.category, m.created_at
               FROM memories m
               JOIN memories_fts f ON m.rowid = f.rowid
               WHERE memories_fts MATCH ? AND m.user_id = ?
               AND (m.expires_at IS NULL OR m.expires_at > datetime('now'))
               ORDER BY bm25(memories_fts)
               LIMIT ?""",
            (sanitized, user_id, limit),
        )
        rows = await cursor.fetchall()
        return [{"content": row[0], "category": row[1], "created_at": row[2]} for row in rows]
    except Exception as exc:
        logger.warning("FTS5 search error: %s", exc)
        return []


async def recall_query_history(
    db: aiosqlite.Connection,
    user_id: str,
    topic: str,
    limit: int = 5,
) -> list[dict]:
    """Find past query snapshots on a topic.

    Args:
        db: Open aiosqlite connection.
        user_id: User identifier.
        topic: One of spending, prices, products, stores, trends, other.
        limit: Maximum results to return.

    Returns:
        List of snapshot dicts ordered by recency, or empty list if invalid topic.
    """
    if topic not in VALID_TOPICS:
        return []

    cursor = await db.execute(
        """SELECT query_text, topic, response_summary, data_snapshot, created_at
           FROM query_snapshots
           WHERE user_id = ? AND topic = ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (user_id, topic, limit),
    )
    rows = await cursor.fetchall()
    return [
        {
            "query_text": row[0],
            "topic": row[1],
            "response_summary": row[2],
            "data_snapshot": row[3],
            "created_at": row[4],
        }
        for row in rows
    ]


async def log_query_snapshot(
    db: aiosqlite.Connection,
    user_id: str,
    query_text: str,
    topic: str,
    response_summary: str,
    data_snapshot: dict,
) -> dict:
    """Record current query and key result values for future comparison.

    Args:
        db: Open aiosqlite connection.
        user_id: User identifier.
        query_text: The user's original query.
        topic: One of spending, prices, products, stores, trends, other.
        response_summary: Brief summary of the response.
        data_snapshot: Dict of key data values (capped at 4KB JSON).

    Returns:
        Dict with status and id.
    """
    if topic not in VALID_TOPICS:
        return {"status": "error", "message": f"Invalid topic: {topic}"}

    snapshot_json = json.dumps(data_snapshot, default=str)
    if len(snapshot_json) > MAX_SNAPSHOT_BYTES:
        return {
            "status": "error",
            "message": f"data_snapshot exceeds {MAX_SNAPSHOT_BYTES} byte limit "
            f"({len(snapshot_json)} bytes). Reduce the snapshot data.",
        }

    snapshot_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO query_snapshots (id, user_id, query_text, topic,
           response_summary, data_snapshot, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (snapshot_id, user_id, query_text, topic, response_summary, snapshot_json, now),
    )
    await db.commit()
    return {"status": "saved", "id": snapshot_id}


async def get_recent_memories(
    db: aiosqlite.Connection,
    user_id: str,
    limit: int = 20,
) -> list[dict]:
    """Fetch recent memories for system prompt injection.

    Args:
        db: Open aiosqlite connection.
        user_id: User identifier.
        limit: Maximum memories to return.

    Returns:
        List of memory dicts with content, category, created_at.
    """
    cursor = await db.execute(
        """SELECT content, category, created_at
           FROM memories
           WHERE user_id = ?
           AND (expires_at IS NULL OR expires_at > datetime('now'))
           ORDER BY updated_at DESC
           LIMIT ?""",
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [{"content": row[0], "category": row[1], "created_at": row[2]} for row in rows]
