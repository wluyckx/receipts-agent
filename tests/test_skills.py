"""
Tests for the Receipts Agent skill registry and skill content.

CHANGELOG:
- 2026-03-19: Initial creation (STORY-078)
"""

from pathlib import Path

from app.skills.registry import SKILLS, classify_skills, get_skill_index, load_skills


class TestClassifySkills:
    """classify_skills should return correct skill IDs based on keywords."""

    def test_classify_spending_keywords(self):
        """Spending-related words should match spending-analytics."""
        result = classify_skills("How much did I spend last month?")
        assert "spending-analytics" in result

    def test_classify_price_keywords(self):
        """Price-related words should match price-tracking."""
        result = classify_skills("What is the cheapest milk?")
        assert "price-tracking" in result

    def test_classify_schema_keywords(self):
        """Schema-related words should match receipt-schema."""
        result = classify_skills("Show me the table schema")
        assert "receipt-schema" in result

    def test_classify_list_keywords(self):
        """Shopping list words should match smart-list."""
        result = classify_skills("What do I need to buy?")
        assert "smart-list" in result

    def test_classify_dutch_keywords(self):
        """Dutch keywords should match correct skills."""
        result = classify_skills("Hoeveel heb ik besteed bij Colruyt?")
        assert "spending-analytics" in result

        result2 = classify_skills("Wat is de prijs van melk?")
        assert "price-tracking" in result2

        result3 = classify_skills("Wat heb ik nodig voor boodschappen?")
        assert "smart-list" in result3

    def test_classify_no_match(self):
        """Messages with no matching keywords should return empty list."""
        result = classify_skills("Hello, how are you?")
        assert result == []

    def test_classify_multiple_skills(self):
        """A query touching multiple domains should return multiple skills."""
        result = classify_skills("Compare spending by category and find the cheapest store")
        assert "spending-analytics" in result
        assert "price-tracking" in result


class TestLoadSkills:
    """load_skills should read and concatenate skill markdown files."""

    def test_load_skills_reads_files(self):
        """Loading a valid skill should return non-empty content."""
        content = load_skills(["receipt-schema"])
        assert len(content) > 100

    def test_load_skills_multiple(self):
        """Loading multiple skills should include content from both."""
        content = load_skills(["spending-analytics", "price-tracking"])
        assert "Spending Analytics" in content
        assert "Price Tracking" in content

    def test_load_skills_empty_list(self):
        """Empty skill list should return empty string."""
        content = load_skills([])
        assert content == ""

    def test_load_skills_unknown_skill(self):
        """Unknown skill ID should be silently skipped."""
        content = load_skills(["nonexistent-skill"])
        assert content == ""


class TestSkillFilesExist:
    """All registered skills must have existing SKILL.md files."""

    def test_all_skill_files_exist(self):
        """Every entry in SKILLS should have a SKILL.md file on disk."""
        for skill_id, meta in SKILLS.items():
            path = Path(meta["file"])
            assert path.exists(), f"Skill file missing for {skill_id}: {meta['file']}"

    def test_skill_content_not_empty(self):
        """Each skill file should have at least 100 characters of content."""
        for skill_id, meta in SKILLS.items():
            path = Path(meta["file"])
            content = path.read_text()
            assert len(content) > 100, f"Skill {skill_id} content too short: {len(content)} chars"


class TestSkillIndex:
    """get_skill_index should produce a compact listing of all skills."""

    def test_skill_index_lists_all(self):
        """Index should contain all 4 skill names."""
        index = get_skill_index()
        assert "receipt-schema" in index
        assert "spending-analytics" in index
        assert "price-tracking" in index
        assert "smart-list" in index


class TestSkillContent:
    """Skill content files should contain expected patterns."""

    def test_spending_skill_has_sql_patterns(self):
        """Spending analytics skill should contain SQL with SELECT and GROUP BY."""
        content = load_skills(["spending-analytics"])
        assert "SELECT" in content
        assert "GROUP BY" in content

    def test_price_skill_has_join_patterns(self):
        """Price tracking skill should contain JOIN receipts patterns."""
        content = load_skills(["price-tracking"])
        assert "JOIN receipts" in content

    def test_smart_list_skill_has_score_guide(self):
        """Smart list skill should explain urgency_level."""
        content = load_skills(["smart-list"])
        assert "urgency_level" in content

    def test_receipt_schema_has_tables(self):
        """Receipt schema skill should describe core tables."""
        content = load_skills(["receipt-schema"])
        assert "receipts" in content
        assert "product_price_history" in content
        assert "stores" in content
        assert "google_product_taxonomy" in content
