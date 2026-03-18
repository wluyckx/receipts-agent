"""
Configuration via pydantic-settings for the Receipts Agent.

All secrets come from environment variables — never hardcoded.

CHANGELOG:
- 2026-03-18: Initial configuration (STORY-073)

TODO:
- None
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Receipts Agent configuration.

    Required environment variables:
        ANTHROPIC_API_KEY: Anthropic API key for Claude access.
        MCP_URL: URL of the shopping-mcp SSE endpoint.

    Optional (with defaults):
        CLAUDE_MODEL: Claude model to use.
        PORT: A2A server port.
        MAX_MEMORIES: Maximum memories to retain.
        MEMORY_PROMPT_LIMIT: Max memories included in prompt context.
        DATABASE_PATH: Path to SQLite database file.
    """

    ANTHROPIC_API_KEY: str
    MCP_URL: str
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    PORT: int = 9100
    MAX_MEMORIES: int = 200
    MEMORY_PROMPT_LIMIT: int = 20
    DATABASE_PATH: str = "/app/data/memory.db"
