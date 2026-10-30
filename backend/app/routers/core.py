from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.auth import DEMO_USER, issue_token, require_user
from app.config import Settings, get_settings
from app.db import get_session
from app.models import Product, Store
from app.schemas import HealthResponse, ProductOut, StoreOut, TokenResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    """Liveness probe. The frontend calls this on load to wake free-tier hosting."""
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        database=database,
        version=__version__,
    )


@router.post("/api/auth/demo", response_model=TokenResponse, tags=["auth"])
async def demo_login(settings: Settings = Depends(get_settings)) -> TokenResponse:
    """One-click demo sign-in: returns a short-lived JWT for the demo analyst."""
    token, expires_in = issue_token(DEMO_USER, settings)
    return TokenResponse(access_token=token, expires_in=expires_in, user=DEMO_USER)


meta = APIRouter(prefix="/api/meta", tags=["meta"], dependencies=[Depends(require_user)])


@meta.get("/stores", response_model=list[StoreOut])
async def list_stores(session: AsyncSession = Depends(get_session)) -> list[StoreOut]:
    stores = (await session.scalars(select(Store).order_by(Store.id))).all()
    return [StoreOut.model_validate(s, from_attributes=True) for s in stores]


@meta.get("/products", response_model=list[ProductOut])
async def list_products(session: AsyncSession = Depends(get_session)) -> list[ProductOut]:
    products = (await session.scalars(select(Product).order_by(Product.id))).all()
    return [
        ProductOut(
            id=p.id,
            sku=p.sku,
            name=p.name,
            category=p.category,
            unit_price=float(p.unit_price),
            lead_time_days=p.lead_time_days,
        )
        for p in products
    ]
