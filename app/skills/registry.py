"""
Skill registry -- keyword-based skill classification and loading.

Skills are markdown files containing domain expertise (SQL patterns, schema
reference, ML score guides). The registry classifies user messages by keywords
and loads matched skill content for system prompt injection.

CHANGELOG:
- 2026-03-19: Initial creation, ported from hestia-agent (STORY-078)

TODO:
- None
"""

from pathlib import Path

SKILLS: dict[str, dict] = {
    "receipt-schema": {
        "keywords": ["schema", "table", "column", "join", "query", "sql"],
        "file": "app/skills/receipt-schema/SKILL.md",
        "description": "Full database schema with column descriptions and JOIN patterns",
    },
    "spending-analytics": {
        "keywords": [
            "spend",
            "spending",
            "category",
            "month",
            "budget",
            "total",
            "breakdown",
            "uitgegeven",
            "besteed",
            "categorie",
        ],
        "file": "app/skills/spending-analytics/SKILL.md",
        "description": "SQL patterns for spending aggregation and category analysis",
    },
    "price-tracking": {
        "keywords": [
            "price",
            "cheap",
            "cheapest",
            "expensive",
            "cost",
            "compare",
            "trend",
            "history",
            "prijs",
            "goedkoop",
            "duur",
        ],
        "file": "app/skills/price-tracking/SKILL.md",
        "description": "SQL patterns for price comparison, trends, and normalization",
    },
    "smart-list": {
        "keywords": [
            "list",
            "need",
            "buy",
            "suggest",
            "prediction",
            "urgency",
            "trip",
            "boodschappen",
            "nodig",
        ],
        "file": "app/skills/smart-list/SKILL.md",
        "description": "ML score interpretation and consumption pattern queries",
    },
    "belgian-context": {
        "keywords": [
            "belgium",
            "belgian",
            "belgi",
            "colruyt",
            "delhaize",
            "lidl",
            "aldi",
            "carrefour",
            "xtra",
            "statiegeld",
            "feestdag",
            "holiday",
        ],
        "file": "app/skills/belgian-context/SKILL.md",
        "description": "Belgian retail landscape, holidays, food culture",
    },
}


def classify_skills(message: str) -> list[str]:
    """Classify which skills are relevant for a user message.

    Uses keyword matching -- fast (~0ms), no API calls.
    Returns list of skill IDs that should be loaded.

    Args:
        message: User message text.

    Returns:
        List of matched skill IDs.
    """
    message_lower = message.lower()
    return [
        skill_id
        for skill_id, meta in SKILLS.items()
        if any(kw in message_lower for kw in meta["keywords"])
    ]


def load_skills(skill_ids: list[str]) -> str:
    """Read and concatenate matched skill markdown files.

    Returns combined skill content for system prompt injection.
    Returns empty string if no skills matched or files missing.

    Args:
        skill_ids: List of skill IDs to load.

    Returns:
        Combined skill content separated by horizontal rules.
    """
    sections = []
    for sid in skill_ids:
        meta = SKILLS.get(sid)
        if not meta:
            continue
        path = Path(meta["file"])
        if path.exists():
            sections.append(path.read_text().strip())
    return "\n\n---\n\n".join(sections) if sections else ""


def get_skill_index() -> str:
    """Build a compact skill index for the base system prompt.

    Returns ~1 line per skill: name + description. Helps Claude
    understand what expertise is available even before skills load.

    Returns:
        Formatted index string.
    """
    lines = ["**Available expertise** (loaded on demand):"]
    for skill_id, meta in SKILLS.items():
        lines.append(f"- {skill_id}: {meta['description']}")
    return "\n".join(lines)
