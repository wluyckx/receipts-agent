"""
Tests for configuration module (pydantic-settings).

CHANGELOG:
- 2026-03-18: Initial config tests (STORY-073)
"""

import pytest


class TestSettings:
    """Test Settings configuration via pydantic-settings."""

    def test_defaults_applied(self, env_defaults):
        """Settings should apply default values for optional fields."""
        from app.config import Settings

        settings = Settings()
        assert settings.PORT == 9100
        assert settings.CLAUDE_MODEL == "claude-sonnet-4-20250514"
        assert settings.MAX_MEMORIES == 200
        assert settings.MEMORY_PROMPT_LIMIT == 20
        assert settings.DATABASE_PATH == "/app/data/memory.db"

    def test_anthropic_key_required(self, monkeypatch):
        """Settings should require ANTHROPIC_API_KEY."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("MCP_URL", "http://test:8000/sse")

        from app.config import Settings

        with pytest.raises(Exception):
            Settings()

    def test_mcp_url_required(self, monkeypatch):
        """Settings should require MCP_URL."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("MCP_URL", raising=False)

        from app.config import Settings

        with pytest.raises(Exception):
            Settings()

    def test_custom_values(self, monkeypatch):
        """Settings should accept custom values from environment."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-custom")
        monkeypatch.setenv("MCP_URL", "http://custom:9000/sse")
        monkeypatch.setenv("PORT", "9200")
        monkeypatch.setenv("CLAUDE_MODEL", "claude-opus-4-20250514")
        monkeypatch.setenv("MAX_MEMORIES", "500")
        monkeypatch.setenv("MEMORY_PROMPT_LIMIT", "50")
        monkeypatch.setenv("DATABASE_PATH", "/tmp/custom.db")

        from app.config import Settings

        settings = Settings()
        assert settings.ANTHROPIC_API_KEY == "sk-custom"
        assert settings.MCP_URL == "http://custom:9000/sse"
        assert settings.PORT == 9200
        assert settings.CLAUDE_MODEL == "claude-opus-4-20250514"
        assert settings.MAX_MEMORIES == 500
        assert settings.MEMORY_PROMPT_LIMIT == 50
        assert settings.DATABASE_PATH == "/tmp/custom.db"

    def test_no_hardcoded_secrets(self):
        """Verify Settings class has no default values for secrets."""
        import inspect

        from app.config import Settings

        source = inspect.getsource(Settings)
        # API key must not have a default value
        assert "ANTHROPIC_API_KEY" in source
        assert "sk-" not in source
