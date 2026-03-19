"""
A2A AgentExecutor and Agent Card for the Receipts Agent.

Implements a Claude tool-use loop that forwards MCP tools to shopping-mcp
and handles local memory tools for persistent insights.

CHANGELOG:
- 2026-03-19: Integrate skill classification and progressive loading (STORY-078)
- 2026-03-18: Claude tool-use loop, memory tools, 4 real skills (STORY-074)
- 2026-03-18: Initial echo executor and agent card (STORY-073)

TODO:
- None
"""

import json
import logging

import aiosqlite
import anthropic
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message

from app import memory
from app.mcp_client import MCPClient
from app.prompts import build_system_prompt
from app.skills.registry import classify_skills, load_skills

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10
CLAUDE_TIMEOUT = 120  # seconds — max time for a single Claude API call

# Default user_id — single-user agent for now
DEFAULT_USER_ID = "default"

# --------------------------------------------------------------------------
# MCP tool definitions exposed to Claude
# --------------------------------------------------------------------------
MCP_TOOL_NAMES = {
    "query_readonly",
    "spending_by_category",
    "spending_by_store",
    "price_history",
    "purchase_frequency",
    "last_purchase",
    "receipt_summary",
    "list_tables",
    "describe_table",
}

MEMORY_TOOL_NAMES = {
    "save_insight",
    "search_memories",
    "recall_query_history",
    "log_query_snapshot",
}

TOOL_DEFINITIONS = [
    # MCP tools — schemas match actual shopping-mcp tool signatures (mcp_server/app.py)
    {
        "name": "query_readonly",
        "description": (
            "Execute a read-only SQL query against the shopping receipts PostgreSQL "
            "database. Returns JSON rows. Max 100 rows. Only SELECT allowed. "
            "30-second timeout. Use this for ad-hoc queries not covered by curated tools."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A read-only SQL SELECT query.",
                },
            },
            "required": ["sql"],
        },
    },
    {
        "name": "spending_by_category",
        "description": (
            "Get spending breakdown by taxonomy parent category with localised names. "
            "Returns category, total_cents, item_count."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "months": {
                    "type": "integer",
                    "description": "Number of months to look back (default 1)",
                },
                "language": {
                    "type": "string",
                    "description": "Locale for category names — nl, fr, or en (default nl)",
                },
            },
        },
    },
    {
        "name": "spending_by_store",
        "description": (
            "Get spending totals by store brand for the last N months. "
            "Returns store, trips, total_cents, savings_cents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "months": {
                    "type": "integer",
                    "description": "Number of months to look back (default 1)",
                },
            },
        },
    },
    {
        "name": "price_history",
        "description": (
            "Get price history for a product over time. Searches by product name substring. "
            "Returns product_name, unit_cents, date, store."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": 'Product name or partial name (e.g. "mozzarella")',
                },
                "months": {
                    "type": "integer",
                    "description": "How many months of history (default 6)",
                },
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "purchase_frequency",
        "description": (
            "Get purchase frequency and pattern for a product concept. "
            "Returns product_name, purchase_count, first/last_purchase, avg_price_cents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": 'Product name or partial name (e.g. "boter", "eggs")',
                },
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "last_purchase",
        "description": (
            "Find when a product was last purchased. "
            "Returns product_name, unit_cents, purchase_ts, store."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": 'Product name or partial name (e.g. "melk", "kefir")',
                },
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "receipt_summary",
        "description": (
            "Get a summary of recent receipts. "
            "Returns date, store, total_cents, xtra_savings_cents, items."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back (default 7)",
                },
            },
        },
    },
    {
        "name": "list_tables",
        "description": (
            "List all available tables and views in the shopping database with row counts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "describe_table",
        "description": "Show columns, types, and constraints for a table.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table or view to describe",
                },
            },
            "required": ["table_name"],
        },
    },
    # Memory tools
    {
        "name": "save_insight",
        "description": (
            "Save a derived insight to persistent memory for future reference. "
            "Use when you discover patterns, preferences, or facts worth remembering."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The insight to save"},
                "category": {
                    "type": "string",
                    "enum": ["insight", "user_context", "observation"],
                    "description": "Category: insight, user_context, or observation",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "search_memories",
        "description": "Search stored memories using full-text search. Check before answering.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "recall_query_history",
        "description": (
            "Recall past query snapshots on a topic for comparison. "
            "Topics: spending, prices, products, stores, trends, other."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": ["spending", "prices", "products", "stores", "trends", "other"],
                    "description": "Topic to recall",
                },
                "limit": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "log_query_snapshot",
        "description": (
            "Record the current query and key result values for future comparison. "
            "Call after answering a query."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query_text": {"type": "string", "description": "The user's original query"},
                "topic": {
                    "type": "string",
                    "enum": ["spending", "prices", "products", "stores", "trends", "other"],
                    "description": "Query topic",
                },
                "response_summary": {"type": "string", "description": "Brief response summary"},
                "data_snapshot": {
                    "type": "object",
                    "description": "Key data values from the response",
                },
            },
            "required": ["query_text", "topic", "response_summary", "data_snapshot"],
        },
    },
]


def create_agent_card(public_url: str = "http://receipts-agent:9100") -> AgentCard:
    """Create the A2A Agent Card for the Receipts Agent.

    Args:
        public_url: URL where this agent is reachable by clients (Docker hostname).

    Returns:
        Configured AgentCard with name, capabilities, and 4 skills.
    """
    # Ensure URL ends with /
    card_url = public_url.rstrip("/") + "/"
    return AgentCard(
        name="Receipts Agent",
        description=(
            "Analyzes shopping receipts, tracks spending patterns, "
            "monitors prices, and provides purchase insights."
        ),
        url=card_url,
        version="0.2.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="query_receipts",
                name="Query Receipts",
                description="Answer questions about purchase history and receipt details.",
                tags=["shopping", "receipts", "history"],
                examples=[
                    "What did I buy at Colruyt last week?",
                    "Show me my last 5 receipts",
                ],
            ),
            AgentSkill(
                id="spending_analysis",
                name="Spending Analysis",
                description=("Analyze spending patterns by category, store, or time period."),
                tags=["spending", "analysis", "budget"],
                examples=[
                    "How much did I spend on groceries last month?",
                    "Compare my spending at Colruyt vs Spar",
                ],
            ),
            AgentSkill(
                id="price_comparison",
                name="Price Comparison",
                description="Compare prices across stores and track price changes over time.",
                tags=["prices", "comparison", "trends"],
                examples=[
                    "Show me price trends for milk",
                    "Which store has the cheapest dairy?",
                ],
            ),
            AgentSkill(
                id="smart_list",
                name="Smart Shopping List",
                description=(
                    "Generate shopping suggestions based on purchase patterns "
                    "and ML-scored urgency."
                ),
                tags=["shopping", "list", "suggestions"],
                examples=[
                    "What do I need to buy soon?",
                    "What are my most frequently purchased items?",
                ],
            ),
        ],
    )


class ReceiptsAgentExecutor(AgentExecutor):
    """A2A executor with Claude tool-use loop for receipt analysis.

    Uses Claude to process user queries with access to shopping-mcp tools
    (for receipt database queries) and local memory tools (for persistent insights).

    Args:
        settings: Application settings with API keys and config.
        db_path: Path to SQLite memory database.
    """

    def __init__(self, settings, db_path: str):
        self.settings = settings
        self.db_path = db_path
        self.mcp_client = MCPClient(settings.MCP_URL)
        self.anthropic = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=CLAUDE_TIMEOUT,
        )

    async def _execute_mcp_tool(self, tool_name: str, tool_input: dict) -> str:
        """Forward a tool call to the MCP server.

        Uses MCPClient.call_tool() which manages session lifecycle,
        automatic reconnection, and error handling.

        Args:
            tool_name: Name of the MCP tool.
            tool_input: Tool input parameters.

        Returns:
            Tool result as string.

        Raises:
            RuntimeError: If MCP returns an error.
        """
        return await self.mcp_client.call_tool(tool_name, tool_input)

    async def _execute_memory_tool(
        self, db: aiosqlite.Connection, tool_name: str, tool_input: dict
    ) -> str:
        """Execute a local memory tool.

        Args:
            db: Open aiosqlite connection.
            tool_name: Memory tool name.
            tool_input: Tool input parameters.

        Returns:
            JSON-serialized result.
        """
        if tool_name == "save_insight":
            result = await memory.save_insight(
                db,
                DEFAULT_USER_ID,
                tool_input["content"],
                category=tool_input.get("category", "insight"),
                max_memories=self.settings.MAX_MEMORIES,
            )
        elif tool_name == "search_memories":
            result = await memory.search_memories(
                db,
                DEFAULT_USER_ID,
                tool_input["query"],
                limit=tool_input.get("limit", 5),
            )
        elif tool_name == "recall_query_history":
            result = await memory.recall_query_history(
                db,
                DEFAULT_USER_ID,
                tool_input["topic"],
                limit=tool_input.get("limit", 5),
            )
        elif tool_name == "log_query_snapshot":
            result = await memory.log_query_snapshot(
                db,
                DEFAULT_USER_ID,
                tool_input["query_text"],
                tool_input["topic"],
                tool_input["response_summary"],
                tool_input.get("data_snapshot", {}),
            )
        else:
            result = {"error": f"Unknown memory tool: {tool_name}"}

        return json.dumps(result, default=str)

    async def _execute_tool(
        self, db: aiosqlite.Connection, tool_name: str, tool_input: dict
    ) -> str:
        """Route a tool call to MCP or local memory handler.

        Args:
            db: Open aiosqlite connection.
            tool_name: Tool name from Claude's tool_use block.
            tool_input: Tool input parameters.

        Returns:
            Tool result as string.
        """
        if tool_name in MEMORY_TOOL_NAMES:
            return await self._execute_memory_tool(db, tool_name, tool_input)
        elif tool_name in MCP_TOOL_NAMES:
            try:
                return await self._execute_mcp_tool(tool_name, tool_input)
            except RuntimeError as exc:
                logger.warning("MCP tool error for %s: %s", tool_name, exc)
                return json.dumps({"error": str(exc)})
            except Exception as exc:
                logger.error("MCP connection error for %s: %s", tool_name, exc)
                return json.dumps({"error": "Database is currently unavailable"})
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Process an incoming A2A message with Claude tool-use loop.

        1. Extract user query from A2A message
        2. Open SQLite db, get recent memories
        3. Build system prompt with memories
        4. Call Claude with system prompt + tools
        5. Tool-use loop (max MAX_TOOL_ROUNDS rounds)
        6. Return final text response via event_queue

        Args:
            context: The A2A request context containing the user message.
            event_queue: Queue for sending response events.
        """
        # 1. Extract user query (get_user_input returns a string in a2a-sdk)
        user_text = context.get_user_input() or ""

        logger.info("Processing query: %s", user_text[:100])

        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 2. Get recent memories
                recent = await memory.get_recent_memories(
                    db, DEFAULT_USER_ID, limit=self.settings.MEMORY_PROMPT_LIMIT
                )

                # 3. Classify and load skills for this query
                # Always load receipt-schema — every query needs schema context
                skill_ids = classify_skills(user_text)
                if "receipt-schema" not in skill_ids:
                    skill_ids.append("receipt-schema")
                skills_content = load_skills(skill_ids)

                # 4. Build system prompt with skills
                system_prompt = build_system_prompt(
                    memories=recent if recent else None,
                    skills_content=skills_content,
                )

                # 5-8. Claude tool-use loop
                messages = [{"role": "user", "content": user_text}]

                for _round in range(MAX_TOOL_ROUNDS):
                    response = await self.anthropic.messages.create(
                        model=self.settings.CLAUDE_MODEL,
                        max_tokens=4096,
                        system=system_prompt,
                        tools=TOOL_DEFINITIONS,
                        messages=messages,
                    )

                    if response.stop_reason == "end_turn":
                        # Extract text content
                        text_parts = [
                            block.text for block in response.content if block.type == "text"
                        ]
                        final_text = "\n".join(text_parts) if text_parts else ""
                        await event_queue.enqueue_event(new_agent_text_message(final_text))
                        return

                    if response.stop_reason == "tool_use":
                        # Process tool calls
                        tool_results = []
                        for block in response.content:
                            if block.type == "tool_use":
                                result = await self._execute_tool(db, block.name, block.input)
                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": block.id,
                                        "content": result,
                                    }
                                )

                        messages.append({"role": "assistant", "content": response.content})
                        messages.append({"role": "user", "content": tool_results})

                # Max rounds reached
                logger.warning(
                    "Max tool rounds (%d) reached, returning partial response",
                    MAX_TOOL_ROUNDS,
                )
                # Try to extract any text from last response
                partial_text = ""
                if response and response.content:
                    text_parts = [block.text for block in response.content if block.type == "text"]
                    partial_text = "\n".join(text_parts)

                if not partial_text:
                    partial_text = (
                        "I was working on your request but reached the maximum "
                        "number of processing steps. Here's what I found so far — "
                        "please try a more specific question."
                    )

                await event_queue.enqueue_event(new_agent_text_message(partial_text))

        except Exception as exc:
            logger.error("Agent execution error: %s", exc, exc_info=True)
            await event_queue.enqueue_event(
                new_agent_text_message(
                    "I'm having trouble processing that right now. Please try again in a moment."
                )
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel is not supported.

        Raises:
            NotImplementedError: Always, as cancellation is not supported.
        """
        raise NotImplementedError("Receipts Agent does not support cancellation")
