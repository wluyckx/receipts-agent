"""
Tests for Receipts Agent memory tools.

CHANGELOG:
- 2026-03-18: Memory tool tests (STORY-074)
"""

import pytest
import pytest_asyncio

from app.database import init_database

USER_ID = "test-user-1"


@pytest_asyncio.fixture
async def memory_db(tmp_path):
    """Provide an initialized SQLite database for memory tests."""
    import aiosqlite

    db_path = str(tmp_path / "test_memory.db")
    await init_database(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        yield db


class TestSanitizeFts5Query:
    """FTS5 query sanitization."""

    def test_sanitize_fts5_query_removes_operators(self):
        """Should remove AND, OR, NOT, NEAR and special chars."""
        from app.memory import sanitize_fts5_query

        result = sanitize_fts5_query('dairy AND "organic" OR NOT milk')
        assert "AND" not in result.split()
        assert "OR" not in result.split()
        assert "NOT" not in result.split()
        assert '"' not in result
        # Should keep the words
        assert "dairy" in result
        assert "milk" in result
        assert "organic" in result

    def test_sanitize_fts5_query_removes_special_chars(self):
        """Should remove parens, colons, asterisks, carets."""
        from app.memory import sanitize_fts5_query

        result = sanitize_fts5_query("content:milk* (organic)^2")
        assert ":" not in result
        assert "*" not in result
        assert "(" not in result
        assert ")" not in result
        assert "^" not in result

    def test_sanitize_fts5_query_keeps_words(self):
        """Plain words should pass through unchanged."""
        from app.memory import sanitize_fts5_query

        result = sanitize_fts5_query("colruyt dairy products")
        assert result.strip() == "colruyt dairy products"

    def test_sanitize_fts5_query_empty_input(self):
        """Empty string should return empty."""
        from app.memory import sanitize_fts5_query

        result = sanitize_fts5_query("")
        assert result.strip() == ""


class TestSaveInsight:
    """Test save_insight memory tool."""

    @pytest.mark.asyncio
    async def test_save_insight_stores_in_db(self, memory_db):
        """save_insight should insert a row into the memories table."""
        from app.memory import save_insight

        result = await save_insight(memory_db, USER_ID, "Colruyt is cheapest for dairy")
        assert result["status"] == "saved"
        assert "id" in result

        cursor = await memory_db.execute(
            "SELECT content, category FROM memories WHERE user_id = ?", (USER_ID,)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "Colruyt is cheapest for dairy"
        assert row[1] == "insight"

    @pytest.mark.asyncio
    async def test_save_insight_dedup_upserts(self, memory_db):
        """Same content_hash should update existing (upsert), not create duplicate."""
        from app.memory import save_insight

        await save_insight(memory_db, USER_ID, "Milk is expensive")
        result = await save_insight(memory_db, USER_ID, "Milk is expensive")
        assert result["status"] == "updated"
        assert "id" in result

        cursor = await memory_db.execute(
            "SELECT COUNT(*) FROM memories WHERE user_id = ?", (USER_ID,)
        )
        row = await cursor.fetchone()
        assert row[0] == 1

    @pytest.mark.asyncio
    async def test_save_insight_capacity_enforcement(self, memory_db):
        """Should evict oldest memories when over max_memories limit."""
        from app.memory import save_insight

        # Insert 5 memories with max_memories=3
        for i in range(5):
            await save_insight(memory_db, USER_ID, f"unique memory {i}", max_memories=3)

        cursor = await memory_db.execute(
            "SELECT COUNT(*) FROM memories WHERE user_id = ?", (USER_ID,)
        )
        row = await cursor.fetchone()
        assert row[0] <= 3

    @pytest.mark.asyncio
    async def test_save_insight_categories(self, memory_db):
        """Should accept valid categories: insight, user_context, observation."""
        from app.memory import save_insight

        for cat in ("insight", "user_context", "observation"):
            result = await save_insight(memory_db, USER_ID, f"test {cat}", category=cat)
            assert result["status"] == "saved"

    @pytest.mark.asyncio
    async def test_save_insight_invalid_category(self, memory_db):
        """Should reject invalid category."""
        from app.memory import save_insight

        result = await save_insight(memory_db, USER_ID, "test", category="invalid")
        assert result["status"] == "error"


class TestSearchMemories:
    """Test search_memories FTS5 search."""

    @pytest.mark.asyncio
    async def test_search_memories_finds_match(self, memory_db):
        """FTS5 search should return matching memories."""
        from app.memory import save_insight, search_memories

        await save_insight(memory_db, USER_ID, "Colruyt is cheapest for dairy products")
        await save_insight(memory_db, USER_ID, "Spar has good bread selection")

        results = await search_memories(memory_db, USER_ID, "dairy")
        assert len(results) >= 1
        assert any("dairy" in r["content"].lower() for r in results)

    @pytest.mark.asyncio
    async def test_search_memories_sanitizes_input(self, memory_db):
        """FTS5 special chars should be escaped without error."""
        from app.memory import save_insight, search_memories

        await save_insight(memory_db, USER_ID, "test content for sanitization")

        # These should not raise even with special FTS5 operators
        results = await search_memories(memory_db, USER_ID, 'content AND "test" OR NOT milk')
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_memories_no_results(self, memory_db):
        """Should return empty list for unmatched query."""
        from app.memory import search_memories

        results = await search_memories(memory_db, USER_ID, "xyzzyx")
        assert results == []


class TestRecallQueryHistory:
    """Test recall_query_history snapshot tool."""

    @pytest.mark.asyncio
    async def test_recall_query_history(self, memory_db):
        """Should return snapshots ordered by recency."""
        from app.memory import log_query_snapshot, recall_query_history

        await log_query_snapshot(
            memory_db, USER_ID, "spending q1", "spending", "spent 100", {"total": 100}
        )
        await log_query_snapshot(
            memory_db, USER_ID, "spending q2", "spending", "spent 200", {"total": 200}
        )

        results = await recall_query_history(memory_db, USER_ID, "spending")
        assert len(results) == 2
        # Most recent first
        assert "200" in results[0]["response_summary"]

    @pytest.mark.asyncio
    async def test_recall_query_history_validates_topic(self, memory_db):
        """Should reject invalid topic."""
        from app.memory import recall_query_history

        result = await recall_query_history(memory_db, USER_ID, "invalid_topic")
        assert isinstance(result, list)
        assert len(result) == 0 or result == []


class TestLogQuerySnapshot:
    """Test log_query_snapshot storage."""

    @pytest.mark.asyncio
    async def test_log_query_snapshot(self, memory_db):
        """Should store snapshot in query_snapshots table."""
        from app.memory import log_query_snapshot

        result = await log_query_snapshot(
            memory_db, USER_ID, "How much spent?", "spending", "Total: €50", {"total": 5000}
        )
        assert result["status"] == "saved"

        cursor = await memory_db.execute(
            "SELECT query_text, topic, data_snapshot FROM query_snapshots WHERE user_id = ?",
            (USER_ID,),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "How much spent?"
        assert row[1] == "spending"

    @pytest.mark.asyncio
    async def test_log_query_snapshot_data_limit_rejects_oversized(self, memory_db):
        """data_snapshot exceeding 4KB should be rejected (not truncated)."""
        from app.memory import log_query_snapshot

        big_data = {"values": "x" * 5000}
        result = await log_query_snapshot(
            memory_db, USER_ID, "big query", "spending", "summary", big_data
        )
        assert result["status"] == "error"
        assert "limit" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_log_query_snapshot_small_data_ok(self, memory_db):
        """data_snapshot under 4KB should be saved normally."""
        from app.memory import log_query_snapshot

        small_data = {"total": 5000, "items": 42}
        result = await log_query_snapshot(
            memory_db, USER_ID, "small query", "spending", "summary", small_data
        )
        assert result["status"] == "saved"


class TestGetRecentMemories:
    """Test get_recent_memories for prompt injection."""

    @pytest.mark.asyncio
    async def test_get_recent_memories(self, memory_db):
        """Should return N most recent memories."""
        from app.memory import get_recent_memories, save_insight

        for i in range(5):
            await save_insight(memory_db, USER_ID, f"memory number {i}")

        results = await get_recent_memories(memory_db, USER_ID, limit=3)
        assert len(results) == 3
        # Should have content and category fields
        assert "content" in results[0]
        assert "category" in results[0]

    @pytest.mark.asyncio
    async def test_get_recent_memories_excludes_expired(self, memory_db):
        """Expired memories should not be returned."""
        import uuid
        from datetime import datetime, timedelta, timezone

        from app.memory import get_recent_memories

        now = datetime.now(timezone.utc)
        past = (now - timedelta(days=1)).isoformat()
        now_str = now.isoformat()

        # Insert an expired memory directly
        await memory_db.execute(
            "INSERT INTO memories (id, user_id, category, content, content_hash, "
            "created_at, updated_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                USER_ID,
                "insight",
                "expired insight",
                "h_exp",
                now_str,
                now_str,
                past,
            ),
        )
        # Insert a non-expired memory
        await memory_db.execute(
            "INSERT INTO memories (id, user_id, category, content, content_hash, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), USER_ID, "insight", "valid insight", "h_val", now_str, now_str),
        )
        await memory_db.commit()

        results = await get_recent_memories(memory_db, USER_ID)
        contents = [r["content"] for r in results]
        assert "valid insight" in contents
        assert "expired insight" not in contents
