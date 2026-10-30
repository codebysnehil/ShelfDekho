import asyncio
import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import Settings, get_settings
from app.db import engine, get_session
from app.jobs import forecast
from app.schemas import DataStatus, ImportRecord, ImportReport, ImportResult
from app.services import dashboard, imports

router = APIRouter(prefix="/api/data", tags=["data"], dependencies=[Depends(require_user)])

MAX_BYTES = 8 * 1024 * 1024
Kind = Literal["sales", "stock"]

# One import at a time: each one ends by rewriting every forecast.
_import_lock = asyncio.Lock()


async def _read_file(request: Request) -> str:
    body = await request.body()
    if len(body) > MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "This file is too big. Send at most 8 MB."
        )
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "We couldn't read this file. Save it from your spreadsheet as CSV and try again.",
        ) from exc


async def _parse(request: Request, kind: Kind, session: AsyncSession) -> imports.Parsed:
    content = await _read_file(request)
    catalog = await imports.load_catalog(session)
    try:
        return imports.parse(kind, content, catalog)
    except imports.FileProblem as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/status", response_model=DataStatus)
async def data_status(
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)
) -> DataStatus:
    head = (
        await session.execute(
            text(
                """
                SELECT (SELECT MAX(as_of) FROM inventory) AS stock_to,
                       (SELECT COUNT(*) FROM stores) AS stores,
                       (SELECT COUNT(*) FROM products) AS products
                """
            )
        )
    ).one()
    history = (
        await session.execute(
            text(
                """
                SELECT created_at, kind, filename, rows_added, date_from, date_to
                FROM data_imports ORDER BY created_at DESC, id DESC LIMIT 5
                """
            )
        )
    ).all()
    return DataStatus(
        sales_to=await dashboard.data_as_of(session),
        stock_to=head.stock_to,
        stores=head.stores,
        products=head.products,
        can_add=settings.data_writes_enabled,
        history=[ImportRecord(**r._mapping) for r in history],
    )


@router.get("/sample/{kind}", response_class=PlainTextResponse)
async def sample(kind: Kind, session: AsyncSession = Depends(get_session)) -> str:
    stores = (await session.scalars(text("SELECT code FROM stores ORDER BY id LIMIT 3"))).all()
    skus = (await session.scalars(text("SELECT sku FROM products ORDER BY id LIMIT 3"))).all()
    last = await session.scalar(text("SELECT MAX(sale_date) FROM daily_sales"))
    day = (last + dt.timedelta(days=1)) if last else dt.date.today()
    return imports.sample_csv(kind, list(stores), list(skus), day)


@router.post("/check", response_model=ImportReport)
async def check(
    request: Request,
    kind: Kind = Query(),
    session: AsyncSession = Depends(get_session),
) -> ImportReport:
    """Read a file and say what it would do. Changes nothing."""
    parsed = await _parse(request, kind, session)
    return await imports.report(session, parsed)


@router.post("/import", response_model=ImportResult)
async def import_file(
    request: Request,
    kind: Kind = Query(),
    filename: str = Query(default="upload.csv", max_length=200),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ImportResult:
    """Save a file's good rows, move stock on, and recalculate every forecast."""
    if not settings.data_writes_enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Adding figures is switched off in this demo, so everyone sees the same store data. "
            "Checking a file still works.",
        )
    parsed = await _parse(request, kind, session)
    summary = await imports.report(session, parsed)
    if not parsed.rows:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "No row in this file could be used."
        )
    # Release this request's connection before the long part below.
    await session.rollback()
    if _import_lock.locked():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Another file is being added. Try again in a minute."
        )
    async with _import_lock:
        await imports.save(engine, parsed, filename, summary)
        await forecast.run(engine)
    return ImportResult(report=summary)
