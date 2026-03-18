"""
MCP client wrapper for connecting to shopping-mcp service.

Provides methods to list available tools and execute SQL queries
via the shopping-mcp SSE endpoint. Manages a persistent session
with automatic reconnection on failure.

CHANGELOG:
- 2026-03-18: Session lifecycle fix — proper context manager, reuse, close (STORY-074 review)
- 2026-03-18: Initial MCP client wrapper (STORY-073)

TODO:
- None
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Timeout for SSE connection establishment (seconds)
SSE_CONNECT_TIMEOUT = 10.0
# Timeout for SSE read operations (seconds)
SSE_READ_TIMEOUT = 60.0


class MCPClient:
    """Wrapper around MCP ClientSession for shopping-mcp communication.

    Maintains a persistent session with automatic reconnection.
    Call close() on shutdown to release resources.

    Args:
        mcp_url: URL of the MCP SSE endpoint (e.g., http://shopping-mcp:8000/sse).
    """

    def __init__(self, mcp_url: str) -> None:
        self.mcp_url = mcp_url
        self._session: Any = None
        self._sse_cm: Any = None  # SSE context manager
        self._session_cm: Any = None  # ClientSession context manager

    async def _ensure_session(self) -> Any:
        """Get or create an initialized MCP ClientSession.

        Reuses existing session if available. Creates a new one if
        the session is None or has been closed. Handles reconnection
        on failure.

        Returns:
            An initialized ClientSession ready for tool calls.
        """
        if self._session is not None:
            return self._session

        from mcp import ClientSession
        from mcp.client.sse import sse_client

        logger.info("Connecting to MCP server at %s", self.mcp_url)

        self._sse_cm = sse_client(
            self.mcp_url,
            timeout=SSE_CONNECT_TIMEOUT,
            sse_read_timeout=SSE_READ_TIMEOUT,
        )
        read_stream, write_stream = await self._sse_cm.__aenter__()

        self._session_cm = ClientSession(read_stream, write_stream)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()

        logger.info("MCP session established")
        return self._session

    async def _reset_session(self) -> None:
        """Close and discard the current session so next call reconnects."""
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:
                pass
        if self._sse_cm is not None:
            try:
                await self._sse_cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._session = None
        self._session_cm = None
        self._sse_cm = None

    async def close(self) -> None:
        """Cleanly close the MCP session and SSE connection."""
        await self._reset_session()
        logger.info("MCP client closed")

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call an MCP tool by name with automatic reconnection.

        Args:
            tool_name: Name of the MCP tool to call.
            arguments: Tool input parameters.

        Returns:
            Tool result as a string.

        Raises:
            RuntimeError: If the MCP tool returns an error.
        """
        try:
            session = await self._ensure_session()
            result = await session.call_tool(tool_name, arguments)
        except Exception as exc:
            # Session may be stale — reset and retry once
            logger.warning("MCP call failed, reconnecting: %s", exc)
            await self._reset_session()
            session = await self._ensure_session()
            result = await session.call_tool(tool_name, arguments)

        if result.isError:
            error_text = result.content[0].text if result.content else "Unknown error"
            raise RuntimeError(f"MCP tool error: {error_text}")

        return result.content[0].text if result.content else ""

    async def list_tools(self) -> list[str]:
        """List available tools from the MCP server.

        Returns:
            List of tool names available on the MCP server.
        """
        session = await self._ensure_session()
        result = await session.list_tools()
        tool_names = [tool.name for tool in result.tools]
        logger.info("MCP tools available: %s", tool_names)
        return tool_names

    async def execute_query(self, sql: str) -> str:
        """Execute a read-only SQL query via the query_readonly MCP tool.

        Convenience method that calls call_tool("query_readonly", ...).

        Args:
            sql: SQL query string to execute.

        Returns:
            Query result as a string (typically JSON).

        Raises:
            RuntimeError: If the MCP tool returns an error.
        """
        return await self.call_tool("query_readonly", {"sql": sql})
