"""
SQLite database initialization for Receipts Agent persistent memory.

Creates memories table with FTS5 full-text search, query_snapshots table,
and auto-sync triggers. Cleans up expired memories during initialization.

CHANGELOG:
- 2026-03-18: Initial schema with FTS5 and cleanup (STORY-073)

TODO:
- None
"""

import logging
import sqlite3
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('insight','user_context','observation')),
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT DEFAULT NULL,
    UNIQUE(user_id, category, content_hash)
);

CREATE TABLE IF NOT EXISTS query_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    query_text TEXT NOT NULL,
    topic TEXT NOT NULL CHECK(topic IN ('spending','prices','products','stores','trends','other')),
    response_summary TEXT NOT NULL,
    data_snapshot TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, category,
    content=memories, content_rowid=rowid,
    tokenize='porter unicode61'
);
"""

TRIGGERS_SQL = """
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, category)
    VALUES (new.rowid, new.content, new.category);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category)
    VALUES('delete', old.rowid, old.content, old.category);
    INSERT INTO memories_fts(rowid, content, category)
    VALUES (new.rowid, new.content, new.category);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category)
    VALUES('delete', old.rowid, old.content, old.category);
END;
"""


async def check_fts5_available() -> None:
    """Verify FTS5 extension is available in the SQLite build.

    Raises:
        RuntimeError: If FTS5 is not available.
    """
    try:
        async with aiosqlite.connect(":memory:") as db:
            await db.execute("CREATE VIRTUAL TABLE _fts5_check USING fts5(c)")
            await db.execute("DROP TABLE _fts5_check")
        logger.info("FTS5 availability confirmed")
    except Exception as exc:
        raise RuntimeError(
            "FTS5 is not available in this SQLite build. "
            "Receipts Agent requires FTS5 for memory search. "
            f"SQLite version: {sqlite3.sqlite_version}"
        ) from exc


async def init_database(db_path: str) -> None:
    """Initialize the memory database schema and clean up expired entries.

    Creates tables, FTS5 virtual table, and triggers if they don't exist.
    Removes any memories whose expires_at timestamp is in the past.

    Args:
        db_path: Path to the SQLite database file.
    """
    await check_fts5_available()

    async with aiosqlite.connect(db_path) as db:
        # Enable WAL mode for concurrent reads
        await db.execute("PRAGMA journal_mode=WAL")

        # Create base tables
        await db.executescript(SCHEMA_SQL)

        # Create FTS5 virtual table
        await db.executescript(FTS_SQL)

        # Create auto-sync triggers
        await db.executescript(TRIGGERS_SQL)

        await db.commit()

        # Clean up expired memories
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info("Cleaned up %d expired memories", deleted)
            await db.commit()

    logger.info("Database initialized: %s", db_path)
