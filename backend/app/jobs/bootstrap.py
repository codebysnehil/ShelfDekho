"""Make a fresh deployment demo-ready: seed data and forecasts if they are missing.

Runs on every container start, so it must be cheap when there is nothing to do.
"""

import asyncio
import logging

from sqlalchemy import func, select

from app.db import engine
from app.jobs import forecast, seed
from app.logging_config import configure_logging
from app.models import ForecastRun

log = logging.getLogger(__name__)


async def bootstrap() -> None:
    await seed.seed(engine)
    async with engine.connect() as conn:
        runs = await conn.scalar(select(func.count()).select_from(ForecastRun))
    if not runs:
        await forecast.run(engine)
    await engine.dispose()


def main() -> None:
    configure_logging()
    asyncio.run(bootstrap())
    log.info("bootstrap complete")


if __name__ == "__main__":
    main()
