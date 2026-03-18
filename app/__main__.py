"""
Entry point for the Receipts Agent A2A server.

Builds the Agent Card, initializes the database, and starts the
A2A Starlette application with health endpoint.

CHANGELOG:
- 2026-03-18: Pass settings and db_path to executor (STORY-074)
- 2026-03-18: Initial entry point (STORY-073)

TODO:
- None
"""

import asyncio
import logging

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.agent import ReceiptsAgentExecutor, create_agent_card
from app.config import Settings
from app.database import check_fts5_available, init_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def health(request):
    """Health check endpoint — returns 200 with status ok."""
    return JSONResponse({"status": "ok"})


async def startup(settings: Settings) -> None:
    """Run startup checks and initialize database."""
    logger.info("Checking FTS5 availability...")
    await check_fts5_available()

    logger.info("Initializing database at %s...", settings.DATABASE_PATH)
    await init_database(settings.DATABASE_PATH)

    logger.info("Startup complete")


def main() -> None:
    """Build and run the Receipts Agent A2A server."""
    settings = Settings()

    logger.info("Starting Receipts Agent on port %d", settings.PORT)

    # Run startup tasks
    asyncio.run(startup(settings))

    # Build A2A application
    agent_card = create_agent_card(public_url=settings.PUBLIC_URL)

    handler = DefaultRequestHandler(
        agent_executor=ReceiptsAgentExecutor(settings=settings, db_path=settings.DATABASE_PATH),
        task_store=InMemoryTaskStore(),
    )

    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    )

    # Build the Starlette app with health route
    starlette_app = a2a_app.build()
    starlette_app.routes.append(Route("/health", health))

    # Run with uvicorn
    uvicorn.run(
        starlette_app,
        host="0.0.0.0",
        port=settings.PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
