import asyncio
import os

# Configure before any app module is imported: the engine is created at import time.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://shelfiq:shelfiq@localhost:5433/shelfiq_test"
)
os.environ.pop("ANALYST_DATABASE_URL", None)
os.environ.pop("REDIS_URL", None)
os.environ["GROQ_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.jobs import forecast, seed  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services import synthetic  # noqa: E402


async def _reset_database() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    # A small but realistic slice: 3 stores x 12 SKUs x 2 years.
    stores = [s for s in synthetic.STORES if s.code in ("DEL01", "MUM01", "PUN01")]
    products = [
        p
        for p in synthetic.PRODUCTS
        if p.sku.endswith(("001", "003")) or p.sku in ("SNB-003", "DRY-001")
    ]
    await seed.seed(engine, force=True, stores=stores, products=products)
    await forecast.run(engine)


def _database_available() -> bool:
    async def probe() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        asyncio.run(probe())
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def seeded_db() -> None:
    if not _database_available():
        pytest.skip("Postgres not reachable; start it with `docker compose up -d db`")
    asyncio.run(_reset_database())


@pytest.fixture
async def client(seeded_db) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        token = (await c.post("/api/auth/demo")).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
