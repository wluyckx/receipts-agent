"""
Tests for Receipts Agent system prompt construction.

CHANGELOG:
- 2026-03-18: Prompt content tests (STORY-074)
"""


class TestPromptSchema:
    """System prompt must include key database schema tables."""

    def test_prompt_contains_receipts_table(self):
        """Prompt should reference the receipts table and its key columns."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert "receipts" in prompt.lower()
        assert "receipt_hash" in prompt
        assert "total_cents" in prompt

    def test_prompt_contains_product_price_history(self):
        """Prompt should reference the product_price_history table."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert "product_price_history" in prompt
        assert "article_nr" in prompt
        assert "unit_cents" in prompt

    def test_prompt_contains_stores(self):
        """Prompt should reference the stores table."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert "stores" in prompt
        assert "brand" in prompt
        assert "store_id" in prompt

    def test_prompt_contains_taxonomy(self):
        """Prompt should reference google_product_taxonomy."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert "google_product_taxonomy" in prompt
        assert "category_path" in prompt

    def test_prompt_contains_smart_list(self):
        """Prompt should reference smart_list_scores."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert "smart_list_scores" in prompt
        assert "urgency_level" in prompt


class TestPromptConstraints:
    """System prompt must contain safety and context constraints."""

    def test_prompt_contains_readonly_constraint(self):
        """Prompt must instruct no INSERT/UPDATE/DELETE."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        prompt_upper = prompt.upper()
        assert any(kw in prompt_upper for kw in ("READ-ONLY", "READ ONLY", "READONLY"))
        # Must mention forbidden operations
        assert "INSERT" in prompt_upper
        assert "UPDATE" in prompt_upper
        assert "DELETE" in prompt_upper

    def test_prompt_contains_belgian_context(self):
        """Prompt should mention Colruyt, EUR cents, Brussels."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert "Colruyt" in prompt
        assert "cents" in prompt.lower()
        assert "Brussels" in prompt or "brussels" in prompt

    def test_prompt_contains_memory_instructions(self):
        """Prompt should instruct the agent to use memory tools."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert "save_insight" in prompt
        assert "search_memories" in prompt


class TestPromptMemories:
    """System prompt memory injection."""

    def test_prompt_with_memories(self):
        """Memories should be formatted and injected into prompt text."""
        from app.prompts import build_system_prompt

        memories = [
            {
                "category": "insight",
                "content": "Colruyt is cheapest for dairy",
                "created_at": "2026-03-15T10:00:00",
            },
            {
                "category": "user_context",
                "content": "User prefers Colruyt",
                "created_at": "2026-03-10T08:00:00",
            },
        ]
        prompt = build_system_prompt(memories=memories)
        assert "Colruyt is cheapest for dairy" in prompt
        assert "User prefers Colruyt" in prompt
        assert "insight" in prompt
        assert "user_context" in prompt

    def test_prompt_without_memories(self):
        """Prompt should work fine with no memories (no error)."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt(memories=None)
        assert len(prompt) > 100
        # No memories section header when empty
        prompt2 = build_system_prompt(memories=[])
        assert len(prompt2) > 100
