"""Bring new figures in from a CSV: daily sales from the tills, or a stock count.

A file is always checked first, without touching the data, so the person sees what will
go in and what will not. Good rows are then saved, stock is moved on by what sold since
the last count, and forecasts are recalculated.
"""

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.schemas import ImportIssue, ImportReport

Kind = Literal["sales", "stock"]

MAX_ROWS = 100_000
MAX_ISSUES = 10
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")

# Accepted headings for each field, as tills and spreadsheets tend to name them.
ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "sale_date", "bill_date", "counted_on", "as_of"),
    "store": ("store", "store_code", "store_name", "outlet"),
    "sku": ("sku", "sku_code", "item_code", "product_code"),
    "units": ("units", "qty", "quantity", "units_sold"),
    "revenue": ("revenue", "sales", "amount", "net_sales"),
    "discount": ("discount", "discount_pct", "promo_discount"),
    "on_hand": ("on_hand", "stock", "closing_stock", "units_on_hand"),
}
REQUIRED: dict[Kind, tuple[str, ...]] = {
    "sales": ("date", "store", "sku", "units"),
    "stock": ("store", "sku", "on_hand"),
}


class FileProblem(ValueError):
    """The file as a whole cannot be read. The message is shown to the person."""


@dataclass(frozen=True)
class Catalog:
    stores: dict[str, int]  # code and name, lower case
    products: dict[str, tuple[int, Decimal, Decimal]]  # sku, lower case: id, price, cost
    today: dt.date


@dataclass
class Parsed:
    kind: Kind
    rows: list[dict] = field(default_factory=list)
    rejected: int = 0
    issues: list[ImportIssue] = field(default_factory=list)


async def load_catalog(conn, today: dt.date | None = None) -> Catalog:
    stores: dict[str, int] = {}
    for s in (await conn.execute(text("SELECT id, code, name FROM stores"))).all():
        stores[s.code.lower()] = s.id
        stores[s.name.lower()] = s.id
    products = {
        p.sku.lower(): (p.id, p.unit_price, p.unit_cost)
        for p in (
            await conn.execute(text("SELECT id, sku, unit_price, unit_cost FROM products"))
        ).all()
    }
    return Catalog(stores, products, today or dt.date.today())


def _parse_date(raw: str) -> dt.date:
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'"{raw}" is not a date we can read. Use 2026-10-26 or 26-10-2026')


def _whole_number(raw: str, label: str) -> int:
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        raise ValueError(f'{label} "{raw}" is not a number') from None
    if value < 0 or value != value.to_integral_value():
        raise ValueError(f'{label} "{raw}" must be a whole number, 0 or more')
    return int(value)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_row(kind: Kind, cells: dict[str, str], catalog: Catalog) -> dict:
    store_id = catalog.stores.get(cells["store"].lower())
    if store_id is None:
        raise ValueError(f'store "{cells["store"]}" is not one of your stores')
    product = catalog.products.get(cells["sku"].lower())
    if product is None:
        raise ValueError(f'SKU "{cells["sku"]}" is not in your product list')
    product_id, price, cost = product

    if kind == "stock":
        on_hand = _whole_number(cells["on_hand"], "stock")
        day = _parse_date(cells["date"]) if cells.get("date") else catalog.today
        if day > catalog.today:
            raise ValueError(f"the date {day.isoformat()} is in the future")
        return {"store_id": store_id, "product_id": product_id, "on_hand": on_hand, "as_of": day}

    day = _parse_date(cells["date"])
    if day > catalog.today:
        raise ValueError(f"the date {day.isoformat()} is in the future")
    units = _whole_number(cells["units"], "units")

    discount = Decimal(0)
    if cells.get("discount"):
        try:
            discount = Decimal(cells["discount"].rstrip("%"))
        except InvalidOperation:
            raise ValueError(f'discount "{cells["discount"]}" is not a number') from None
        if discount > 1:  # 15 and 0.15 both mean 15% off
            discount /= 100
        if not 0 <= discount <= Decimal("0.9"):
            raise ValueError(f'discount "{cells["discount"]}" must be between 0 and 90%')

    if cells.get("revenue"):
        try:
            revenue = Decimal(cells["revenue"].replace(",", ""))
        except InvalidOperation:
            raise ValueError(f'revenue "{cells["revenue"]}" is not a number') from None
        if revenue < 0:
            raise ValueError(f'revenue "{cells["revenue"]}" cannot be negative')
    else:
        revenue = price * (1 - discount) * units

    return {
        "sale_date": day,
        "store_id": store_id,
        "product_id": product_id,
        "units": units,
        "revenue": _money(revenue),
        "cost": _money(cost * units),
        "promo_discount": discount.quantize(Decimal("0.01")),
    }


def parse(kind: Kind, content: str, catalog: Catalog) -> Parsed:
    """Read a whole file, keeping good rows and noting the first few bad ones."""
    reader = csv.reader(io.StringIO(content))
    headings = [h.strip().lower().replace(" ", "_") for h in next(reader, [])]
    columns: dict[str, int] = {}
    for name, accepted in ALIASES.items():
        for i, heading in enumerate(headings):
            if heading in accepted:
                columns[name] = i
                break
    missing = [name for name in REQUIRED[kind] if name not in columns]
    if missing:
        raise FileProblem(
            f"This file needs a column for {', '.join(missing)}. "
            "Download the sample file to see the layout."
        )

    parsed = Parsed(kind)
    keys: dict[tuple, int] = {}
    for line, raw in enumerate(reader, start=2):
        if not any(cell.strip() for cell in raw):
            continue
        if line > MAX_ROWS + 1:
            raise FileProblem(f"This file is too long. Send at most {MAX_ROWS:,} rows at a time.")
        cells = {
            name: raw[i].strip() if i < len(raw) else "" for name, i in columns.items()
        }
        try:
            for name in REQUIRED[kind]:
                if not cells[name]:
                    raise ValueError(f"{name} is empty")
            row = _parse_row(kind, cells, catalog)
            key = (row.get("sale_date"), row["store_id"], row["product_id"])
            if key in keys:
                raise ValueError(f"same {'day, ' if kind == 'sales' else ''}store and SKU as line {keys[key]}")
            keys[key] = line
            parsed.rows.append(row)
        except ValueError as problem:
            parsed.rejected += 1
            if len(parsed.issues) < MAX_ISSUES:
                parsed.issues.append(ImportIssue(line=line, problem=str(problem)))
    return parsed


async def report(conn, parsed: Parsed) -> ImportReport:
    """What the file would do, in the person's terms."""
    rows = parsed.rows
    date_key = "sale_date" if parsed.kind == "sales" else "as_of"
    dates = [r[date_key] for r in rows]
    replaces = 0
    if parsed.kind == "sales" and rows:
        existing = await conn.execute(
            text(
                """
                SELECT sale_date, store_id, product_id FROM daily_sales
                WHERE sale_date BETWEEN :start AND :end
                """
            ),
            {"start": min(dates), "end": max(dates)},
        )
        have = {tuple(r) for r in existing.all()}
        replaces = sum((r["sale_date"], r["store_id"], r["product_id"]) in have for r in rows)
    return ImportReport(
        kind=parsed.kind,
        rows_ok=len(rows),
        rows_rejected=parsed.rejected,
        rows_replacing=replaces,
        date_from=min(dates) if dates else None,
        date_to=max(dates) if dates else None,
        stores=len({r["store_id"] for r in rows}),
        products=len({r["product_id"] for r in rows}),
        issues=parsed.issues,
    )


async def save(engine: AsyncEngine, parsed: Parsed, filename: str, summary: ImportReport) -> None:
    """Save the good rows in one transaction, so a failure leaves the figures as they were."""
    async with engine.begin() as conn:
        if parsed.kind == "sales":
            await _save_sales(conn, parsed.rows)
        else:
            await conn.execute(
                text(
                    """
                    INSERT INTO inventory (store_id, product_id, on_hand, as_of)
                    VALUES (:store_id, :product_id, :on_hand, :as_of)
                    ON CONFLICT (store_id, product_id)
                    DO UPDATE SET on_hand = EXCLUDED.on_hand, as_of = EXCLUDED.as_of
                    """
                ),
                parsed.rows,
            )
        await conn.execute(
            text(
                """
                INSERT INTO data_imports (kind, filename, rows_added, date_from, date_to)
                VALUES (:kind, :filename, :rows, :date_from, :date_to)
                """
            ),
            {
                "kind": parsed.kind,
                "filename": filename[:120],
                "rows": summary.rows_ok,
                "date_from": summary.date_from,
                "date_to": summary.date_to,
            },
        )


async def _save_sales(conn, rows: list[dict]) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO daily_sales
                (sale_date, store_id, product_id, units, revenue, cost, promo_discount)
            VALUES (:sale_date, :store_id, :product_id, :units, :revenue, :cost, :promo_discount)
            ON CONFLICT (sale_date, store_id, product_id) DO UPDATE SET
                units = EXCLUDED.units, revenue = EXCLUDED.revenue,
                cost = EXCLUDED.cost, promo_discount = EXCLUDED.promo_discount
            """
        ),
        rows,
    )
    # Sales after the last count have left the shelf. Older days are already in that count.
    counted = {
        (r.store_id, r.product_id): r
        for r in (
            await conn.execute(text("SELECT store_id, product_id, on_hand, as_of FROM inventory"))
        ).all()
    }
    moved: dict[tuple[int, int], dict] = {}
    for row in rows:
        key = (row["store_id"], row["product_id"])
        stock = counted.get(key)
        if stock is None or row["sale_date"] <= stock.as_of:
            continue
        entry = moved.setdefault(key, {"sold": 0, "as_of": stock.as_of, "on_hand": stock.on_hand})
        entry["sold"] += row["units"]
        entry["as_of"] = max(entry["as_of"], row["sale_date"])
    if moved:
        await conn.execute(
            text(
                """
                UPDATE inventory SET on_hand = :on_hand, as_of = :as_of
                WHERE store_id = :store_id AND product_id = :product_id
                """
            ),
            [
                {
                    "store_id": store_id,
                    "product_id": product_id,
                    "on_hand": max(0, e["on_hand"] - e["sold"]),
                    "as_of": e["as_of"],
                }
                for (store_id, product_id), e in moved.items()
            ],
        )


def sample_csv(kind: Kind, stores: list[str], skus: list[str], day: dt.date) -> str:
    """A small file in the right layout, using this business's own stores and SKUs."""
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    if kind == "sales":
        writer.writerow(["date", "store", "sku", "units", "revenue", "discount"])
        for i, (store, sku) in enumerate(zip(stores, skus, strict=False)):
            writer.writerow([day.isoformat(), store, sku, 12 + i * 5, "", "10" if i == 1 else ""])
    else:
        writer.writerow(["date", "store", "sku", "on_hand"])
        for i, (store, sku) in enumerate(zip(stores, skus, strict=False)):
            writer.writerow([day.isoformat(), store, sku, 120 + i * 35])
    return out.getvalue()
