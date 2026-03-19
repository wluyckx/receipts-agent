#!/usr/bin/env python3
"""
Validate all registered skills for consistency.

Checks:
- Every registered skill has an existing SKILL.md file
- SKILL.md files are non-empty and within size limits
- Keywords list is non-empty for each skill
- No orphaned skill directories (registered but missing, or present but unregistered)

Usage:
    python scripts/validate_skills.py

Exit code 0 = all valid, 1 = errors found.

CHANGELOG:
- 2026-03-19: Initial creation (STORY-080)
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.skills.registry import SKILLS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MAX_SKILL_SIZE_BYTES = 10_240  # 10KB per skill file
MIN_SKILL_SIZE_BYTES = 50  # Must have meaningful content


def validate() -> list[str]:
    """Validate all registered skills. Returns list of error messages."""
    errors: list[str] = []

    for skill_id, meta in SKILLS.items():
        keywords = meta.get("keywords", [])
        if not keywords:
            errors.append(f"{skill_id}: empty keywords list")

        file_path = meta.get("file", "")
        if not file_path:
            errors.append(f"{skill_id}: missing 'file' in registry")
            continue

        path = Path(file_path)
        if not path.exists():
            errors.append(f"{skill_id}: SKILL.md not found at {file_path}")
            continue

        size = path.stat().st_size
        if size < MIN_SKILL_SIZE_BYTES:
            errors.append(
                f"{skill_id}: SKILL.md too small ({size}B, min {MIN_SKILL_SIZE_BYTES}B)"
            )
        if size > MAX_SKILL_SIZE_BYTES:
            errors.append(
                f"{skill_id}: SKILL.md too large ({size}B, max {MAX_SKILL_SIZE_BYTES}B)"
            )

        if not meta.get("description"):
            errors.append(f"{skill_id}: missing 'description' in registry")

    # Check for orphaned skill directories
    skills_dir = Path("app/skills")
    if skills_dir.exists():
        for child in skills_dir.iterdir():
            if (
                child.is_dir()
                and (child / "SKILL.md").exists()
                and child.name not in SKILLS
            ):
                errors.append(f"{child.name}: directory exists but not registered")

    return errors


if __name__ == "__main__":
    errs = validate()
    if errs:
        logger.error("FAILED — %d error(s):", len(errs))
        for e in errs:
            logger.error("  - %s", e)
        sys.exit(1)
    else:
        logger.info("OK — %d skills validated", len(SKILLS))
        sys.exit(0)
