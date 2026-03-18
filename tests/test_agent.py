"""
Tests for A2A Agent Card and AgentExecutor.

CHANGELOG:
- 2026-03-18: Initial agent tests (STORY-073)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


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


class TestAgentExecutor:
    """Test the AgentExecutor echo behavior."""

    @pytest.mark.asyncio
    async def test_execute_echoes_message(self):
        """AgentExecutor should echo back the user message."""
        from app.agent import ReceiptsAgentExecutor

        executor = ReceiptsAgentExecutor()

        # Create a mock RequestContext with a user message
        context = MagicMock()
        # The A2A SDK provides the message through context
        message = MagicMock()
        part = MagicMock()
        part.text = "How much did I spend on groceries?"
        message.parts = [part]
        context.get_user_input.return_value = message

        # Create a mock EventQueue
        event_queue = AsyncMock()
        event_queue.enqueue_event = AsyncMock()

        await executor.execute(context, event_queue)

        # Verify that enqueue_event was called with a response
        event_queue.enqueue_event.assert_called_once()
        call_args = event_queue.enqueue_event.call_args
        event = call_args[0][0]
        # The event should contain text with the echoed message
        assert event is not None

    @pytest.mark.asyncio
    async def test_cancel_raises(self):
        """AgentExecutor.cancel should raise NotImplementedError."""
        from app.agent import ReceiptsAgentExecutor

        executor = ReceiptsAgentExecutor()
        context = MagicMock()
        event_queue = AsyncMock()

        with pytest.raises(Exception):
            await executor.cancel(context, event_queue)
