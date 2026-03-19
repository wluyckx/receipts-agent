"""
Tests for Receipts Agent system prompt construction.

CHANGELOG:
- 2026-03-19: Update for skill-based architecture — schema moved to skill (STORY-078)
- 2026-03-18: Prompt content tests (STORY-074)
"""

from app.skills.registry import load_skills


class TestPromptBaseContent:
    """Base system prompt should contain core elements but NOT the schema."""

    def test_base_prompt_does_not_contain_schema(self):
        """Schema is now in the receipt-schema skill, not the base prompt."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        # The old DATABASE_SCHEMA block with table definitions should be gone
        assert "product_price_history (article_nr" not in prompt
        assert "stores (store_id PK" not in prompt

    def test_prompt_contains_efficiency_rules(self):
        """Base prompt should have efficiency rules for 1-2 tool calls."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert "1-2 tool calls" in prompt

    def test_prompt_contains_skill_index(self):
        """Base prompt should include the skill index listing available expertise."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert "Available expertise" in prompt
        assert "receipt-schema" in prompt
        assert "spending-analytics" in prompt


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

    def test_prompt_contains_memory_guidance(self):
        """Prompt should mention memory usage guidance."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert "memory" in prompt.lower()
        assert "insight" in prompt.lower()


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


class TestPromptSkillsContent:
    """System prompt should inject skill content when provided."""

    def test_skills_content_injected(self):
        """Skills content should appear in the prompt when provided."""
        from app.prompts import build_system_prompt

        skills = load_skills(["spending-analytics"])
        prompt = build_system_prompt(skills_content=skills)
        assert "Spending Analytics" in prompt
        assert "SELECT" in prompt

    def test_skills_content_empty_by_default(self):
        """When no skills_content is provided, prompt still works."""
        from app.prompts import build_system_prompt

        prompt = build_system_prompt()
        assert len(prompt) > 100

    def test_skills_content_with_memories(self):
        """Skills content and memories should both appear when provided."""
        from app.prompts import build_system_prompt

        memories = [
            {
                "category": "insight",
                "content": "Test memory",
                "created_at": "2026-03-15T10:00:00",
            },
        ]
        skills = load_skills(["price-tracking"])
        prompt = build_system_prompt(memories=memories, skills_content=skills)
        assert "Test memory" in prompt
        assert "Price Tracking" in prompt
