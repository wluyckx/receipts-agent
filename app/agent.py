"""
A2A AgentExecutor and Agent Card for the Receipts Agent.

The executor currently echoes back user messages as proof of A2A plumbing.
Receipt-specific intelligence will be added in STORY-074.

CHANGELOG:
- 2026-03-18: Initial echo executor and agent card (STORY-073)

TODO:
- STORY-074: Replace echo with Claude-powered receipt analysis
"""

import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message

logger = logging.getLogger(__name__)


def create_agent_card(port: int = 9100) -> AgentCard:
    """Create the A2A Agent Card for the Receipts Agent.

    Args:
        port: Port the agent is running on.

    Returns:
        Configured AgentCard with name, capabilities, and skills.
    """
    return AgentCard(
        name="Receipts Agent",
        description=(
            "Analyzes shopping receipts, tracks spending patterns, "
            "monitors prices, and provides purchase insights."
        ),
        url=f"http://localhost:{port}/",
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="receipt-analysis",
                name="Receipt Analysis",
                description=(
                    "Analyzes shopping receipts to extract spending patterns, "
                    "track prices, and provide purchase insights."
                ),
                tags=["shopping", "receipts", "spending"],
                examples=[
                    "How much did I spend on groceries last month?",
                    "What are my most frequently purchased items?",
                    "Show me price trends for milk",
                ],
            ),
        ],
    )


class ReceiptsAgentExecutor(AgentExecutor):
    """A2A executor for the Receipts Agent.

    Currently echoes back user messages. Will be replaced with
    Claude-powered receipt analysis in STORY-074.
    """

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Process an incoming A2A message.

        For now, echoes back the user's message as proof of A2A connectivity.

        Args:
            context: The A2A request context containing the user message.
            event_queue: Queue for sending response events.
        """
        user_input = context.get_user_input()
        user_text = ""
        if user_input and user_input.parts:
            user_text = user_input.parts[0].text

        response = f"[Receipts Agent echo] {user_text}"
        logger.info("Echo response: %s", response)

        await event_queue.enqueue_event(new_agent_text_message(response))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel is not supported.

        Raises:
            NotImplementedError: Always, as cancellation is not supported.
        """
        raise NotImplementedError("Receipts Agent does not support cancellation")
