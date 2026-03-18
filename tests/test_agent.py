"""
Tests for A2A Agent Card and AgentExecutor.

CHANGELOG:
- 2026-03-18: Claude tool-use loop tests (STORY-074)
- 2026-03-18: Initial agent tests (STORY-073)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.database import init_database


class TestAgentCard:
    """Test Agent Card structure and content."""

    def test_agent_card_has_required_fields(self):
        """Agent card should contain name, description, version, url, capabilities."""
        from app.agent import create_agent_card

        card = create_agent_card(port=9100)
        assert card.name == "Receipts Agent"
        assert card.description is not None
        assert len(card.description) > 0
        assert card.version is not None
        assert card.url == "http://localhost:9100/"
        assert card.capabilities is not None

    def test_agent_card_has_skills(self):
        """Agent card should have at least one placeholder skill."""
        from app.agent import create_agent_card

        card = create_agent_card(port=9100)
        assert card.skills is not None
        assert len(card.skills) >= 1

    def test_agent_card_skill_has_fields(self):
        """Each skill should have id, name, description."""
        from app.agent import create_agent_card

        card = create_agent_card(port=9100)
        skill = card.skills[0]
        assert skill.id is not None
        assert skill.name is not None
        assert skill.description is not None

    def test_agent_card_default_modes(self):
        """Agent card should specify text as default input/output mode."""
        from app.agent import create_agent_card

        card = create_agent_card(port=9100)
        assert "text" in card.default_input_modes
        assert "text" in card.default_output_modes

    def test_agent_card_url_uses_port(self):
        """Agent card URL should reflect the configured port."""
        from app.agent import create_agent_card

        card = create_agent_card(port=9200)
        assert "9200" in card.url

    def test_agent_card_has_four_skills(self):
        """Agent card should have exactly 4 real skills."""
        from app.agent import create_agent_card

        card = create_agent_card(port=9100)
        assert len(card.skills) == 4

    def test_agent_card_skill_ids(self):
        """Skill IDs should match expected values."""
        from app.agent import create_agent_card

        card = create_agent_card(port=9100)
        skill_ids = {s.id for s in card.skills}
        expected = {"query_receipts", "spending_analysis", "price_comparison", "smart_list"}
        assert skill_ids == expected


class TestAgentExecutor:
    """Test the AgentExecutor with Claude tool-use loop."""

    def _make_settings(self):
        """Create a mock Settings object."""
        settings = MagicMock()
        settings.ANTHROPIC_API_KEY = "sk-test-key"
        settings.MCP_URL = "http://shopping-mcp:8000/sse"
        settings.CLAUDE_MODEL = "claude-sonnet-4-20250514"
        settings.MEMORY_PROMPT_LIMIT = 20
        settings.MAX_MEMORIES = 200
        return settings

    def _make_context(self, text="How much did I spend on groceries?"):
        """Create a mock RequestContext with user message."""
        context = MagicMock()
        message = MagicMock()
        part = MagicMock()
        part.text = text
        message.parts = [part]
        context.get_user_input.return_value = message
        return context

    def _make_text_response(self, text="You spent €123.45 on groceries."):
        """Create a mock Claude response with text content."""
        response = MagicMock()
        response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = text
        response.content = [text_block]
        return response

    def _make_tool_use_response(self, tool_name="query_readonly", tool_input=None, tool_id="tu1"):
        """Create a mock Claude response with a tool_use block."""
        if tool_input is None:
            tool_input = {"sql": "SELECT COUNT(*) FROM receipts"}
        response = MagicMock()
        response.stop_reason = "tool_use"
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = tool_name
        tool_block.input = tool_input
        tool_block.id = tool_id
        response.content = [tool_block]
        return response

    @pytest_asyncio.fixture
    async def db_path(self, tmp_path):
        """Create an initialized SQLite database."""
        path = str(tmp_path / "test_agent.db")
        await init_database(path)
        return path

    @pytest.mark.asyncio
    async def test_executor_calls_claude(self, db_path):
        """Executor should call anthropic.messages.create with correct args."""
        from app.agent import ReceiptsAgentExecutor

        settings = self._make_settings()
        executor = ReceiptsAgentExecutor(settings=settings, db_path=db_path)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=self._make_text_response())
        executor.anthropic = mock_client

        context = self._make_context()
        event_queue = AsyncMock()

        await executor.execute(context, event_queue)

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-20250514"
        assert "system" in call_kwargs.kwargs
        assert "tools" in call_kwargs.kwargs
        assert "messages" in call_kwargs.kwargs

    @pytest.mark.asyncio
    async def test_executor_handles_text_response(self, db_path):
        """Simple text response should be returned via event_queue."""
        from app.agent import ReceiptsAgentExecutor

        settings = self._make_settings()
        executor = ReceiptsAgentExecutor(settings=settings, db_path=db_path)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=self._make_text_response("You spent €50.")
        )
        executor.anthropic = mock_client

        context = self._make_context()
        event_queue = AsyncMock()

        await executor.execute(context, event_queue)

        event_queue.enqueue_event.assert_called_once()
        event = event_queue.enqueue_event.call_args[0][0]
        assert "€50" in event["text"]

    @pytest.mark.asyncio
    async def test_executor_handles_tool_use(self, db_path):
        """tool_use block should trigger tool execution and a second Claude call."""
        from app.agent import ReceiptsAgentExecutor

        settings = self._make_settings()
        executor = ReceiptsAgentExecutor(settings=settings, db_path=db_path)

        # Mock MCP client — query_readonly uses execute_query
        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(return_value="42")
        executor.mcp_client = mock_mcp

        # First call returns tool_use, second returns text
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                self._make_tool_use_response(),
                self._make_text_response("There are 42 receipts."),
            ]
        )
        executor.anthropic = mock_client

        context = self._make_context()
        event_queue = AsyncMock()

        await executor.execute(context, event_queue)

        assert mock_client.messages.create.call_count == 2
        event_queue.enqueue_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_executor_multi_round_tool_use(self, db_path):
        """Multiple rounds of tool calls should work."""
        from app.agent import ReceiptsAgentExecutor

        settings = self._make_settings()
        executor = ReceiptsAgentExecutor(settings=settings, db_path=db_path)

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(return_value="data")
        executor.mcp_client = mock_mcp

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                self._make_tool_use_response(tool_id="tu1"),
                self._make_tool_use_response(tool_id="tu2"),
                self._make_text_response("Done."),
            ]
        )
        executor.anthropic = mock_client

        context = self._make_context()
        event_queue = AsyncMock()

        await executor.execute(context, event_queue)

        assert mock_client.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_executor_respects_max_rounds(self, db_path):
        """Should stop after MAX_TOOL_ROUNDS and return a warning."""
        from app.agent import MAX_TOOL_ROUNDS, ReceiptsAgentExecutor

        settings = self._make_settings()
        executor = ReceiptsAgentExecutor(settings=settings, db_path=db_path)

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(return_value="data")
        executor.mcp_client = mock_mcp

        # Always returns tool_use, never text
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                self._make_tool_use_response(tool_id=f"tu{i}") for i in range(MAX_TOOL_ROUNDS + 5)
            ]
        )
        executor.anthropic = mock_client

        context = self._make_context()
        event_queue = AsyncMock()

        await executor.execute(context, event_queue)

        # Should have called create MAX_TOOL_ROUNDS times (not more)
        assert mock_client.messages.create.call_count == MAX_TOOL_ROUNDS
        # Should still return something to the user
        event_queue.enqueue_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_executor_handles_sql_error(self, db_path):
        """SQL error from MCP should return user-friendly message."""
        from app.agent import ReceiptsAgentExecutor

        settings = self._make_settings()
        executor = ReceiptsAgentExecutor(settings=settings, db_path=db_path)

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(side_effect=RuntimeError("MCP tool error: bad SQL"))
        executor.mcp_client = mock_mcp

        # First call: tool_use, but tool execution fails -> error result to Claude
        # Second call: Claude responds with text
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                self._make_tool_use_response(),
                self._make_text_response("Sorry, I had a problem with the query."),
            ]
        )
        executor.anthropic = mock_client

        context = self._make_context()
        event_queue = AsyncMock()

        await executor.execute(context, event_queue)

        # Should still respond (not crash)
        event_queue.enqueue_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_executor_handles_api_error(self, db_path):
        """Anthropic API error should return graceful fallback."""
        from app.agent import ReceiptsAgentExecutor

        settings = self._make_settings()
        executor = ReceiptsAgentExecutor(settings=settings, db_path=db_path)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API connection error"))
        executor.anthropic = mock_client

        context = self._make_context()
        event_queue = AsyncMock()

        await executor.execute(context, event_queue)

        event_queue.enqueue_event.assert_called_once()
        event = event_queue.enqueue_event.call_args[0][0]
        assert "trouble" in event["text"].lower() or "unavailable" in event["text"].lower()

    @pytest.mark.asyncio
    async def test_executor_handles_memory_tool(self, db_path):
        """Memory tool calls should be handled by local memory functions."""
        from app.agent import ReceiptsAgentExecutor

        settings = self._make_settings()
        executor = ReceiptsAgentExecutor(settings=settings, db_path=db_path)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                self._make_tool_use_response(
                    tool_name="save_insight",
                    tool_input={"content": "Colruyt is cheapest", "category": "insight"},
                    tool_id="mem1",
                ),
                self._make_text_response("Noted!"),
            ]
        )
        executor.anthropic = mock_client

        context = self._make_context("Remember that Colruyt is cheapest")
        event_queue = AsyncMock()

        await executor.execute(context, event_queue)

        assert mock_client.messages.create.call_count == 2
        event_queue.enqueue_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_raises(self):
        """AgentExecutor.cancel should raise NotImplementedError."""
        from app.agent import ReceiptsAgentExecutor

        settings = self._make_settings()
        executor = ReceiptsAgentExecutor(settings=settings, db_path="/tmp/test.db")
        context = MagicMock()
        event_queue = AsyncMock()

        with pytest.raises(Exception):
            await executor.cancel(context, event_queue)
