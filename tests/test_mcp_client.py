"""
Tests for MCP client wrapper (mocked — no real shopping-mcp connection).

CHANGELOG:
- 2026-03-18: Session lifecycle tests, call_tool interface (STORY-074 review)
- 2026-03-18: Initial MCP client tests with mocks (STORY-073)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMCPClientListTools:
    """Test MCP client wrapper can list tools from shopping-mcp."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_tool_names(self):
        """list_tools should return a list of available tool names."""
        from app.mcp_client import MCPClient

        mock_tools = MagicMock()
        mock_tools.tools = [
            MagicMock(name="query_readonly", description="Run read-only SQL"),
            MagicMock(name="spending_by_category", description="Category spending"),
        ]
        mock_tools.tools[0].name = "query_readonly"
        mock_tools.tools[1].name = "spending_by_category"

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools)

        client = MCPClient(mcp_url="http://test:8000/sse")

        with patch.object(client, "_ensure_session", return_value=mock_session):
            tools = await client.list_tools()

        assert "query_readonly" in tools
        assert "spending_by_category" in tools

    @pytest.mark.asyncio
    async def test_list_tools_empty(self):
        """list_tools should return empty list when no tools available."""
        from app.mcp_client import MCPClient

        mock_tools = MagicMock()
        mock_tools.tools = []

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools)

        client = MCPClient(mcp_url="http://test:8000/sse")

        with patch.object(client, "_ensure_session", return_value=mock_session):
            tools = await client.list_tools()

        assert tools == []


class TestMCPClientCallTool:
    """Test MCP client call_tool method."""

    @pytest.mark.asyncio
    async def test_call_tool_returns_results(self):
        """call_tool should forward to session and return text result."""
        from app.mcp_client import MCPClient

        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='[{"count": 42}]')]
        mock_result.content[0].text = '[{"count": 42}]'
        mock_result.isError = False

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        client = MCPClient(mcp_url="http://test:8000/sse")

        with patch.object(client, "_ensure_session", return_value=mock_session):
            result = await client.call_tool("query_readonly", {"sql": "SELECT 1"})

        assert result == '[{"count": 42}]'

    @pytest.mark.asyncio
    async def test_call_tool_handles_error(self):
        """call_tool should raise RuntimeError on MCP tool error."""
        from app.mcp_client import MCPClient

        mock_result = MagicMock()
        mock_result.isError = True
        mock_result.content = [MagicMock(text="SQL error: table not found")]
        mock_result.content[0].text = "SQL error: table not found"

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        client = MCPClient(mcp_url="http://test:8000/sse")

        with patch.object(client, "_ensure_session", return_value=mock_session):
            with pytest.raises(RuntimeError, match="MCP tool error"):
                await client.call_tool("query_readonly", {"sql": "SELECT * FROM bad"})

    @pytest.mark.asyncio
    async def test_call_tool_reconnects_on_failure(self):
        """call_tool should reset session and retry on connection error."""
        from app.mcp_client import MCPClient

        mock_result = MagicMock()
        mock_result.content = [MagicMock(text="ok")]
        mock_result.content[0].text = "ok"
        mock_result.isError = False

        # First session fails, second succeeds
        failing_session = AsyncMock()
        failing_session.call_tool = AsyncMock(side_effect=ConnectionError("lost"))

        good_session = AsyncMock()
        good_session.call_tool = AsyncMock(return_value=mock_result)

        client = MCPClient(mcp_url="http://test:8000/sse")
        call_count = 0

        async def mock_ensure():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return failing_session
            return good_session

        with patch.object(client, "_ensure_session", side_effect=mock_ensure):
            with patch.object(client, "_reset_session", new_callable=AsyncMock):
                result = await client.call_tool("list_tables", {})

        assert result == "ok"

    @pytest.mark.asyncio
    async def test_execute_query_convenience(self):
        """execute_query should delegate to call_tool with query_readonly."""
        from app.mcp_client import MCPClient

        client = MCPClient(mcp_url="http://test:8000/sse")
        client.call_tool = AsyncMock(return_value="result")

        result = await client.execute_query("SELECT 1")

        client.call_tool.assert_called_once_with("query_readonly", {"sql": "SELECT 1"})
        assert result == "result"


class TestMCPClientConnection:
    """Test MCP client connection management."""

    def test_client_stores_url(self):
        """MCPClient should store the MCP URL."""
        from app.mcp_client import MCPClient

        client = MCPClient(mcp_url="http://shopping-mcp:8000/sse")
        assert client.mcp_url == "http://shopping-mcp:8000/sse"

    def test_client_starts_without_session(self):
        """MCPClient should start with no active session."""
        from app.mcp_client import MCPClient

        client = MCPClient(mcp_url="http://test:8000/sse")
        assert client._session is None

    @pytest.mark.asyncio
    async def test_close_clears_session(self):
        """close() should clear the session state."""
        from app.mcp_client import MCPClient

        client = MCPClient(mcp_url="http://test:8000/sse")
        client._session = MagicMock()
        client._session_cm = AsyncMock()
        client._sse_cm = AsyncMock()

        await client.close()

        assert client._session is None
        assert client._session_cm is None
        assert client._sse_cm is None
