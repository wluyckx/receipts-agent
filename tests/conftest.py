"""
Shared test fixtures for receipts-agent.

CHANGELOG:
- 2026-03-18: Initial fixtures (STORY-073)
"""

import sys
import types
from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub the a2a package if not installed (offline dev — real package in Docker)
# ---------------------------------------------------------------------------
if "a2a" not in sys.modules:

    @dataclass
    class _AgentCapabilities:
        streaming: bool = False

    @dataclass
    class _AgentSkill:
        id: str = ""
        name: str = ""
        description: str = ""
        tags: list = field(default_factory=list)
        examples: list = field(default_factory=list)

    @dataclass
    class _AgentCard:
        name: str = ""
        description: str = ""
        url: str = ""
        version: str = ""
        default_input_modes: list = field(default_factory=list)
        default_output_modes: list = field(default_factory=list)
        capabilities: _AgentCapabilities = field(default_factory=_AgentCapabilities)
        skills: list = field(default_factory=list)

    class _AgentExecutor:
        async def execute(self, context, event_queue):
            raise NotImplementedError

        async def cancel(self, context, event_queue):
            raise NotImplementedError

    class _RequestContext:
        pass

    class _EventQueue:
        async def enqueue_event(self, event):
            pass

    def _new_agent_text_message(text):
        return {"type": "text", "text": text}

    # Build module tree
    a2a = types.ModuleType("a2a")
    a2a_server = types.ModuleType("a2a.server")
    a2a_server_agent_execution = types.ModuleType("a2a.server.agent_execution")
    a2a_server_events = types.ModuleType("a2a.server.events")
    a2a_server_apps = types.ModuleType("a2a.server.apps")
    a2a_server_request_handlers = types.ModuleType("a2a.server.request_handlers")
    a2a_server_tasks = types.ModuleType("a2a.server.tasks")
    a2a_types = types.ModuleType("a2a.types")
    a2a_utils = types.ModuleType("a2a.utils")

    a2a_server_agent_execution.AgentExecutor = _AgentExecutor
    a2a_server_agent_execution.RequestContext = _RequestContext
    a2a_server_events.EventQueue = _EventQueue
    a2a_types.AgentCapabilities = _AgentCapabilities
    a2a_types.AgentCard = _AgentCard
    a2a_types.AgentSkill = _AgentSkill
    a2a_utils.new_agent_text_message = _new_agent_text_message

    a2a_server_apps.A2AStarletteApplication = MagicMock
    a2a_server_request_handlers.DefaultRequestHandler = MagicMock
    a2a_server_tasks.InMemoryTaskStore = MagicMock

    a2a.server = a2a_server
    a2a_server.agent_execution = a2a_server_agent_execution
    a2a_server.events = a2a_server_events
    a2a_server.apps = a2a_server_apps
    a2a_server.request_handlers = a2a_server_request_handlers
    a2a_server.tasks = a2a_server_tasks
    a2a.types = a2a_types
    a2a.utils = a2a_utils

    sys.modules["a2a"] = a2a
    sys.modules["a2a.server"] = a2a_server
    sys.modules["a2a.server.agent_execution"] = a2a_server_agent_execution
    sys.modules["a2a.server.events"] = a2a_server_events
    sys.modules["a2a.server.apps"] = a2a_server_apps
    sys.modules["a2a.server.request_handlers"] = a2a_server_request_handlers
    sys.modules["a2a.server.tasks"] = a2a_server_tasks
    sys.modules["a2a.types"] = a2a_types
    sys.modules["a2a.utils"] = a2a_utils


@pytest.fixture
def tmp_db_path(tmp_path):
    """Provide a temporary SQLite database path."""
    return str(tmp_path / "test_memory.db")


@pytest.fixture
def env_defaults(monkeypatch):
    """Set minimal environment variables for Settings."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key-for-testing")
    monkeypatch.setenv("MCP_URL", "http://shopping-mcp:8000/sse")
