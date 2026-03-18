"""
MCP client wrapper for connecting to shopping-mcp service.

Provides methods to list available tools and execute SQL queries
via the shopping-mcp SSE endpoint.

CHANGELOG:
- 2026-03-18: Initial MCP client wrapper (STORY-073)

TODO:
- None
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MCPClient:
    """Wrapper around MCP ClientSession for shopping-mcp communication.

    Args:
        mcp_url: URL of the MCP SSE endpoint (e.g., http://shopping-mcp:8000/sse).
    """

    def __init__(self, mcp_url: str) -> None:
        self.mcp_url = mcp_url

    async def _get_session(self) -> Any:
        """Get an initialized MCP ClientSession.

        Returns a connected and initialized ClientSession.
        In production, this connects via SSE transport.
        In tests, this is patched to return a mock.
        """
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        read_stream, write_stream = await sse_client(self.mcp_url).__aenter__()
        session = ClientSession(read_stream, write_stream)
        await session.__aenter__()
        await session.initialize()
        return session

    async def list_tools(self) -> list[str]:
        """List available tools from the MCP server.

        Returns:
            List of tool names available on the MCP server.
        """
        session = await self._get_session()
        result = await session.list_tools()
        tool_names = [tool.name for tool in result.tools]
        logger.info("MCP tools available: %s", tool_names)
        return tool_names

    async def execute_query(self, sql: str) -> str:
        """Execute a read-only SQL query via MCP tool call.

        Args:
            sql: SQL query string to execute.

        Returns:
            Query result as a string (typically JSON).

        Raises:
            RuntimeError: If the MCP tool returns an error.
        """
        session = await self._get_session()
        result = await session.call_tool("query_readonly", {"sql": sql})

        if result.isError:
            error_text = result.content[0].text if result.content else "Unknown error"
            raise RuntimeError(f"MCP tool error: {error_text}")

        return result.content[0].text if result.content else ""
