"""
Tests for MCP client wrapper (mocked — no real shopping-mcp connection).

CHANGELOG:
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
            MagicMock(name="query_write", description="Run write SQL"),
        ]
        # Override .name since MagicMock uses name for its own purposes
        mock_tools.tools[0].name = "query_readonly"
        mock_tools.tools[1].name = "query_write"

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools)

        client = MCPClient(mcp_url="http://test:8000/sse")

        with patch.object(client, "_get_session", return_value=mock_session):
            tools = await client.list_tools()

        assert "query_readonly" in tools
        assert "query_write" in tools

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

        with patch.object(client, "_get_session", return_value=mock_session):
            tools = await client.list_tools()

        assert tools == []


class TestMCPClientQuery:
    """Test MCP client wrapper can execute SQL queries via MCP tools."""

    @pytest.mark.asyncio
    async def test_execute_query_returns_results(self):
        """execute_query should call query_readonly and return results."""
        from app.mcp_client import MCPClient

        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='[{"count": 42}]')]
        mock_result.content[0].text = '[{"count": 42}]'
        mock_result.isError = False

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        client = MCPClient(mcp_url="http://test:8000/sse")

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client.execute_query("SELECT COUNT(*) as count FROM receipts")

        mock_session.call_tool.assert_called_once_with(
            "query_readonly", {"sql": "SELECT COUNT(*) as count FROM receipts"}
        )
        assert result == '[{"count": 42}]'

    @pytest.mark.asyncio
    async def test_execute_query_handles_error(self):
        """execute_query should raise on MCP tool error."""
        from app.mcp_client import MCPClient

        mock_result = MagicMock()
        mock_result.isError = True
        mock_result.content = [MagicMock(text="SQL error: table not found")]
        mock_result.content[0].text = "SQL error: table not found"

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        client = MCPClient(mcp_url="http://test:8000/sse")

        with patch.object(client, "_get_session", return_value=mock_session):
            with pytest.raises(RuntimeError, match="MCP tool error"):
                await client.execute_query("SELECT * FROM nonexistent")


class TestMCPClientConnection:
    """Test MCP client connection management."""

    def test_client_stores_url(self):
        """MCPClient should store the MCP URL."""
        from app.mcp_client import MCPClient

        client = MCPClient(mcp_url="http://shopping-mcp:8000/sse")
        assert client.mcp_url == "http://shopping-mcp:8000/sse"
