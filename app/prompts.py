"""
System prompt construction for the Receipts Agent.

Builds a context-rich prompt with Belgian retail context, safety constraints,
memory injection, and skill-based progressive loading for Claude tool-use
conversations.

CHANGELOG:
- 2026-03-19: Refactor — move schema to receipt-schema skill, add skills_content (STORY-078)
- 2026-03-18: Full system prompt with schema, context, memory injection (STORY-074)
- 2026-03-18: Placeholder created (STORY-073)

TODO:
- None
"""

from app.skills.registry import get_skill_index

BELGIAN_CONTEXT = """\
## Belgian Retail Context

- **Store brands**: Colruyt, Collect&Go (Colruyt online), Okay (Colruyt discount), \
Spar, Bio-Planet
- All monetary values are in **cents** (EUR). Format as €X.XX for display.
- **Timezone**: Europe/Brussels
- **Xtra savings** = Colruyt loyalty discount (xtra_savings_cents on receipts)
- Product names are typically in Dutch (Flemish Belgian market)
- Use `google_category_translations` with locale='nl' for Dutch category names
"""

SAFETY_CONSTRAINTS = """\
## Safety Constraints

- **READ-ONLY SQL ONLY.** Never generate INSERT, UPDATE, DELETE, or DROP statements.
- The MCP server enforces read-only access, but you must also never attempt write \
operations.
- Maximum 100 rows returned per query. Use LIMIT clauses.
"""

MEMORY_INSTRUCTIONS = """\
## Memory (use sparingly)

- Only call memory tools for SIGNIFICANT insights worth remembering long-term.
- Do NOT call search_memories or log_query_snapshot for simple factual queries.
- Save an insight only when you discover a genuinely new pattern (e.g., price trend, \
store preference).
"""

BASE_PROMPT = """\
You are the Receipts Agent, a specialized data assistant for shopping receipts.

## Efficiency Rules
- Answer in 1-2 tool calls maximum.
- Use the SQL patterns provided in your loaded expertise below.
- If an SQL pattern matches, copy it and fill in the placeholders.
- For queries not covered by patterns, write a single precise query_readonly call.
- Return concise data — the orchestrating agent formats the final answer.

{belgian_context}

{safety}

{memory_instructions}

{memories_section}

{skill_index}

{skills_content}
"""


def _format_memories(memories: list[dict]) -> str:
    """Format memory entries for injection into the system prompt.

    Args:
        memories: List of memory dicts with category, content, created_at keys.

    Returns:
        Formatted memories section or empty string if no memories.
    """
    if not memories:
        return ""

    lines = ["## Your Memories"]
    for m in memories:
        category = m.get("category", "insight")
        content = m.get("content", "")
        created = m.get("created_at", "")[:10]  # date portion
        lines.append(f"- [{category}] {content} (saved {created})")

    return "\n".join(lines)


def build_system_prompt(
    memories: list[dict] | None = None,
    skills_content: str = "",
) -> str:
    """Build the full system prompt for Claude with context, memories, and skills.

    The database schema is no longer embedded in the base prompt. It is loaded
    on demand via the receipt-schema skill, keeping the base prompt lean.

    Args:
        memories: Optional list of memory dicts to inject. Each dict should have
            category, content, and created_at keys.
        skills_content: Pre-loaded skill markdown content to inject.

    Returns:
        Complete system prompt string.
    """
    memories_section = _format_memories(memories) if memories else ""

    return BASE_PROMPT.format(
        belgian_context=BELGIAN_CONTEXT,
        safety=SAFETY_CONSTRAINTS,
        memory_instructions=MEMORY_INSTRUCTIONS,
        memories_section=memories_section,
        skill_index=get_skill_index(),
        skills_content=skills_content,
    )
