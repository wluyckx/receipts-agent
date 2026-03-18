"""
Tests for SQLite memory database with FTS5.

CHANGELOG:
- 2026-03-18: Initial database schema and FTS5 tests (STORY-073)
"""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest


class TestFTS5Availability:
    """Verify FTS5 is available in the Python SQLite build."""

    def test_fts5_available(self):
        """FTS5 must be available in bundled SQLite."""
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE _fts5_test USING fts5(content)")
            conn.execute("DROP TABLE _fts5_test")
        except sqlite3.OperationalError:
            pytest.fail("FTS5 is not available in this SQLite build")
        finally:
            conn.close()


class TestMemorySchema:
    """Test memory database schema creation."""

    @pytest.mark.asyncio
    async def test_init_creates_tables(self, tmp_db_path):
        """init_database should create memories and query_snapshots tables."""
        from app.database import init_database

        await init_database(tmp_db_path)

        import aiosqlite

        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in await cursor.fetchall()]
            assert "memories" in tables
            assert "query_snapshots" in tables

    @pytest.mark.asyncio
    async def test_memories_table_columns(self, tmp_db_path):
        """memories table should have correct columns."""
        from app.database import init_database

        await init_database(tmp_db_path)

        import aiosqlite

        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute("PRAGMA table_info(memories)")
            columns = {row[1]: row[2] for row in await cursor.fetchall()}
            assert "id" in columns
            assert "user_id" in columns
            assert "category" in columns
            assert "content" in columns
            assert "content_hash" in columns
            assert "confidence" in columns
            assert "created_at" in columns
            assert "updated_at" in columns
            assert "expires_at" in columns

    @pytest.mark.asyncio
    async def test_category_check_constraint(self, tmp_db_path):
        """memories category must be one of insight/user_context/observation."""
        from app.database import init_database

        await init_database(tmp_db_path)

        import aiosqlite

        async with aiosqlite.connect(tmp_db_path) as db:
            now = datetime.now(timezone.utc).isoformat()
            # Valid category should work
            await db.execute(
                "INSERT INTO memories (id, user_id, category, content, content_hash, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), "user1", "insight", "test", "hash1", now, now),
            )
            await db.commit()

            # Invalid category should fail
            with pytest.raises(sqlite3.IntegrityError):
                await db.execute(
                    "INSERT INTO memories (id, user_id, category, content, content_hash, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), "user1", "invalid_cat", "test", "hash2", now, now),
                )

    @pytest.mark.asyncio
    async def test_query_snapshots_topic_constraint(self, tmp_db_path):
        """query_snapshots topic must be one of the allowed values."""
        from app.database import init_database

        await init_database(tmp_db_path)

        import aiosqlite

        async with aiosqlite.connect(tmp_db_path) as db:
            now = datetime.now(timezone.utc).isoformat()
            # Valid topic should work
            await db.execute(
                "INSERT INTO query_snapshots (id, user_id, query_text, topic, "
                "response_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), "user1", "test query", "spending", "summary", now),
            )
            await db.commit()

            # Invalid topic should fail
            with pytest.raises(sqlite3.IntegrityError):
                await db.execute(
                    "INSERT INTO query_snapshots (id, user_id, query_text, topic, "
                    "response_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), "user1", "test", "invalid_topic", "s", now),
                )


class TestFTS5Integration:
    """Test FTS5 virtual table and auto-sync triggers."""

    @pytest.mark.asyncio
    async def test_fts5_table_created(self, tmp_db_path):
        """init_database should create memories_fts virtual table."""
        from app.database import init_database

        await init_database(tmp_db_path)

        import aiosqlite

        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memories_fts'"
            )
            row = await cursor.fetchone()
            assert row is not None

    @pytest.mark.asyncio
    async def test_fts5_insert_trigger(self, tmp_db_path):
        """Inserting into memories should auto-populate FTS index."""
        from app.database import init_database

        await init_database(tmp_db_path)

        import aiosqlite

        async with aiosqlite.connect(tmp_db_path) as db:
            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "INSERT INTO memories (id, user_id, category, content, content_hash, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), "user1", "insight", "grocery spending pattern", "h1", now, now),
            )
            await db.commit()

            cursor = await db.execute(
                "SELECT content FROM memories_fts WHERE memories_fts MATCH 'grocery'"
            )
            rows = await cursor.fetchall()
            assert len(rows) == 1
            assert "grocery" in rows[0][0]

    @pytest.mark.asyncio
    async def test_fts5_update_trigger(self, tmp_db_path):
        """Updating memories content should update FTS index."""
        from app.database import init_database

        await init_database(tmp_db_path)

        import aiosqlite

        async with aiosqlite.connect(tmp_db_path) as db:
            now = datetime.now(timezone.utc).isoformat()
            mem_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO memories (id, user_id, category, content, content_hash, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mem_id, "user1", "insight", "old content", "h1", now, now),
            )
            await db.commit()

            await db.execute(
                "UPDATE memories SET content = ?, content_hash = ?, updated_at = ? WHERE id = ?",
                ("new shopping data", "h2", now, mem_id),
            )
            await db.commit()

            # Old content should not match
            cursor = await db.execute(
                "SELECT content FROM memories_fts WHERE memories_fts MATCH 'old'"
            )
            assert len(await cursor.fetchall()) == 0

            # New content should match
            cursor = await db.execute(
                "SELECT content FROM memories_fts WHERE memories_fts MATCH 'shopping'"
            )
            assert len(await cursor.fetchall()) == 1

    @pytest.mark.asyncio
    async def test_fts5_delete_trigger(self, tmp_db_path):
        """Deleting from memories should remove from FTS index."""
        from app.database import init_database

        await init_database(tmp_db_path)

        import aiosqlite

        async with aiosqlite.connect(tmp_db_path) as db:
            now = datetime.now(timezone.utc).isoformat()
            mem_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO memories (id, user_id, category, content, content_hash, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mem_id, "user1", "insight", "deletable content", "h1", now, now),
            )
            await db.commit()

            await db.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
            await db.commit()

            cursor = await db.execute(
                "SELECT content FROM memories_fts WHERE memories_fts MATCH 'deletable'"
            )
            assert len(await cursor.fetchall()) == 0


class TestExpiredMemoryCleanup:
    """Test that expired memories are cleaned up during init."""

    @pytest.mark.asyncio
    async def test_expired_memories_removed(self, tmp_db_path):
        """init_database should remove memories with past expires_at."""
        from app.database import init_database

        await init_database(tmp_db_path)

        import aiosqlite

        now = datetime.now(timezone.utc)
        past = (now - timedelta(days=1)).isoformat()
        future = (now + timedelta(days=1)).isoformat()
        now_str = now.isoformat()

        async with aiosqlite.connect(tmp_db_path) as db:
            # Insert expired memory
            await db.execute(
                "INSERT INTO memories (id, user_id, category, content, content_hash, "
                "created_at, updated_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("expired-1", "user1", "insight", "old data", "h1", now_str, now_str, past),
            )
            # Insert non-expired memory
            await db.execute(
                "INSERT INTO memories (id, user_id, category, content, content_hash, "
                "created_at, updated_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("valid-1", "user1", "insight", "fresh data", "h2", now_str, now_str, future),
            )
            # Insert memory with no expiry
            await db.execute(
                "INSERT INTO memories (id, user_id, category, content, content_hash, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("forever-1", "user1", "observation", "permanent", "h3", now_str, now_str),
            )
            await db.commit()

        # Re-init to trigger cleanup
        await init_database(tmp_db_path)

        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute("SELECT id FROM memories ORDER BY id")
            ids = [row[0] for row in await cursor.fetchall()]
            assert "expired-1" not in ids
            assert "valid-1" in ids
            assert "forever-1" in ids

    @pytest.mark.asyncio
    async def test_idempotent_init(self, tmp_db_path):
        """init_database should be safe to call multiple times."""
        from app.database import init_database

        await init_database(tmp_db_path)
        await init_database(tmp_db_path)  # Should not raise


class TestFTS5Check:
    """Test FTS5 availability check at startup."""

    @pytest.mark.asyncio
    async def test_check_fts5_passes(self, tmp_db_path):
        """check_fts5_available should not raise when FTS5 is available."""
        from app.database import check_fts5_available

        # Should not raise
        await check_fts5_available()

    @pytest.mark.asyncio
    async def test_unique_constraint_on_memories(self, tmp_db_path):
        """Duplicate (user_id, category, content_hash) should fail."""
        from app.database import init_database

        await init_database(tmp_db_path)

        import aiosqlite

        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(tmp_db_path) as db:
            await db.execute(
                "INSERT INTO memories (id, user_id, category, content, content_hash, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("id1", "user1", "insight", "content", "same_hash", now, now),
            )
            await db.commit()

            with pytest.raises(sqlite3.IntegrityError):
                await db.execute(
                    "INSERT INTO memories (id, user_id, category, content, content_hash, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("id2", "user1", "insight", "different content", "same_hash", now, now),
                )
