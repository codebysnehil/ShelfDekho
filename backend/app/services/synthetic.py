"""Deterministic synthetic retail dataset.

Two years of daily sales for an Indian grocery and general-merchandise chain. The data
is synthetic (so there are no licensing issues) but it has the structure real retail
data has, plus a few planted stories the dashboard and AI analyst can surface:

* yearly seasonality: summer drinks and sunscreen, monsoon mosquito repellent,
  winter lotion, and a large Diwali spike that moves date every year
* a weekly pattern with weekend peaks
* chain-wide promotions with category-specific price elasticity and a post-promo dip
* Pune Baner loses ~18% of sales after a competitor opens in March 2026
* Hyderabad Gachibowli (a new Express store) grows fast
* supply-chain stockouts: Cola 2L in Mumbai Andheri during the May 2026 heatwave and
  Toned Milk in Delhi Dwarka in July 2026
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

from app.services.calendar import DIWALI

DATA_END = dt.date(2026, 10, 25)  # a Sunday
WEEKS = 104
DATA_START = DATA_END - dt.timedelta(days=WEEKS * 7 - 1)  # a Monday

# Promotions are planned ahead, so the promo calendar runs past the end of the sales data.
PLANNED_WEEKS = 8
COMPETITOR_OPENS = dt.date(2026, 3, 2)


@dataclass(frozen=True)
class StoreSpec:
    code: str
    name: str
    city: str
    region: str
    format: str
    size_sqft: int
    scale: float
    annual_growth: float


@dataclass(frozen=True)
class ProductSpec:
    sku: str
    name: str
    category: str
    price: float
    base_units: float  # daily units at a scale-1.0 store
    lead_time_days: int
    summer: float = 0.0
    monsoon: float = 0.0
    winter: float = 0.0
    festive: float = 0.0


STORES = [
    StoreSpec("DEL01", "Saket", "New Delhi", "North", "Hypermarket", 42000, 1.6, 0.07),
    StoreSpec("DEL02", "Dwarka", "New Delhi", "North", "Supermarket", 18000, 1.0, 0.06),
    StoreSpec("JAI01", "Malviya Nagar", "Jaipur", "North", "Supermarket", 15000, 0.8, 0.08),
    StoreSpec("MUM01", "Andheri", "Mumbai", "West", "Hypermarket", 38000, 1.5, 0.06),
    StoreSpec("PUN01", "Baner", "Pune", "West", "Supermarket", 16000, 0.95, 0.07),
    StoreSpec("BLR01", "Indiranagar", "Bengaluru", "South", "Supermarket", 20000, 1.1, 0.10),
    StoreSpec("HYD01", "Gachibowli", "Hyderabad", "South", "Express", 6000, 0.45, 0.40),
    StoreSpec("CHE01", "Velachery", "Chennai", "South", "Supermarket", 17000, 0.9, 0.06),
]

# Category-level economics: cost as a share of list price, and price elasticity used to
# compute promo lift.
CATEGORIES = {
    "Staples": {"cost_ratio": 0.84, "elasticity": 1.2, "trend": 0.04, "pantry_dip": 0.85},
    "Dairy": {"cost_ratio": 0.80, "elasticity": 0.8, "trend": 0.06, "pantry_dip": 1.0},
    "Snacks & Beverages": {
        "cost_ratio": 0.68,
        "elasticity": 2.2,
        "trend": 0.09,
        "pantry_dip": 0.95,
    },
    "Personal Care": {"cost_ratio": 0.58, "elasticity": 1.8, "trend": 0.15, "pantry_dip": 0.9},
    "Home Care": {"cost_ratio": 0.64, "elasticity": 1.6, "trend": 0.07, "pantry_dip": 0.85},
    "Festive & Gifting": {"cost_ratio": 0.55, "elasticity": 1.0, "trend": 0.12, "pantry_dip": 1.0},
}

P = ProductSpec
PRODUCTS = [
    # Staples
    P("STP-001", "Basmati Rice 5kg", "Staples", 650, 9, 7, festive=0.2),
    P("STP-002", "Toor Dal 1kg", "Staples", 160, 22, 7),
    P("STP-003", "Whole Wheat Atta 10kg", "Staples", 480, 11, 7),
    P("STP-004", "Sunflower Oil 1L", "Staples", 170, 26, 5, festive=0.3),
    P("STP-005", "Sugar 1kg", "Staples", 48, 30, 5, festive=0.35),
    P("STP-006", "Iodised Salt 1kg", "Staples", 28, 24, 5),
    P("STP-007", "Poha 500g", "Staples", 45, 14, 7),
    P("STP-008", "Besan 1kg", "Staples", 110, 10, 7, festive=0.5),
    # Dairy
    P("DRY-001", "Toned Milk 1L", "Dairy", 56, 110, 2, summer=0.05),
    P("DRY-002", "Curd 400g", "Dairy", 40, 45, 2, summer=0.35),
    P("DRY-003", "Paneer 200g", "Dairy", 95, 28, 2, festive=0.5),
    P("DRY-004", "Salted Butter 100g", "Dairy", 58, 20, 3, winter=0.2),
    P("DRY-005", "Cow Ghee 1L", "Dairy", 620, 5, 5, festive=0.8, winter=0.2),
    P("DRY-006", "Cheese Slices 200g", "Dairy", 140, 9, 3),
    P("DRY-007", "Sweet Lassi 200ml", "Dairy", 25, 30, 2, summer=0.9),
    P("DRY-008", "Masala Buttermilk 500ml", "Dairy", 30, 25, 2, summer=1.0),
    # Snacks & Beverages
    P("SNB-001", "Potato Chips 52g", "Snacks & Beverages", 20, 70, 5, festive=0.2),
    P("SNB-002", "Namkeen Mix 400g", "Snacks & Beverages", 110, 16, 5, festive=0.7),
    P("SNB-003", "Cola 2L", "Snacks & Beverages", 95, 22, 4, summer=0.9, festive=0.3),
    P("SNB-004", "Mango Drink 1.2L", "Snacks & Beverages", 75, 18, 4, summer=1.2),
    P("SNB-005", "Green Tea 25 bags", "Snacks & Beverages", 160, 7, 7, winter=0.25),
    P("SNB-006", "Instant Coffee 100g", "Snacks & Beverages", 310, 6, 7, winter=0.3),
    P("SNB-007", "Cream Biscuits 300g", "Snacks & Beverages", 40, 40, 5),
    P("SNB-008", "Dark Chocolate 80g", "Snacks & Beverages", 120, 10, 7, festive=0.9),
    # Personal Care
    P("PRC-001", "Bath Soap 4x100g", "Personal Care", 180, 16, 10),
    P("PRC-002", "Anti-Dandruff Shampoo 340ml", "Personal Care", 320, 7, 10),
    P("PRC-003", "Toothpaste 150g", "Personal Care", 110, 20, 10),
    P("PRC-004", "Face Wash 100ml", "Personal Care", 199, 8, 10, summer=0.2),
    P("PRC-005", "Body Lotion 400ml", "Personal Care", 350, 4, 10, winter=1.2),
    P("PRC-006", "Coconut Hair Oil 300ml", "Personal Care", 190, 9, 10),
    P("PRC-007", "Deodorant 150ml", "Personal Care", 225, 6, 10, summer=0.5),
    P("PRC-008", "Sunscreen SPF50 50g", "Personal Care", 399, 3, 14, summer=1.6),
    # Home Care
    P("HMC-001", "Detergent Powder 2kg", "Home Care", 240, 12, 10),
    P("HMC-002", "Dishwash Liquid 750ml", "Home Care", 160, 13, 10),
    P("HMC-003", "Floor Cleaner 1L", "Home Care", 210, 8, 10, festive=0.6),
    P("HMC-004", "Toilet Cleaner 1L", "Home Care", 180, 9, 10, festive=0.4),
    P("HMC-005", "Agarbatti 100 sticks", "Home Care", 60, 10, 10, festive=1.2),
    P("HMC-006", "Garbage Bags 30pc", "Home Care", 120, 9, 10),
    P("HMC-007", "Mosquito Repellent Refill", "Home Care", 85, 10, 7, monsoon=1.8),
    P("HMC-008", "Air Freshener 240ml", "Home Care", 220, 4, 10, festive=0.5),
    # Festive & Gifting
    P("FST-001", "Dry Fruits Gift Box 500g", "Festive & Gifting", 899, 0.8, 14, festive=9.0),
    P("FST-002", "Kaju Katli 500g", "Festive & Gifting", 550, 1.5, 3, festive=7.0),
    P("FST-003", "Clay Diya Set 12pc", "Festive & Gifting", 149, 0.6, 14, festive=14.0),
    P("FST-004", "Rangoli Colours Pack", "Festive & Gifting", 99, 0.5, 14, festive=12.0),
    P("FST-005", "Premium Gift Hamper", "Festive & Gifting", 1499, 0.3, 14, festive=10.0),
    P("FST-006", "Soan Papdi 500g", "Festive & Gifting", 180, 1.6, 7, festive=6.0),
    P("FST-007", "LED String Lights 10m", "Festive & Gifting", 349, 0.5, 14, festive=11.0),
    P("FST-008", "Brass Puja Thali Set", "Festive & Gifting", 450, 0.4, 14, festive=8.0),
]

WEEKDAY_FACTOR = np.array([0.90, 0.88, 0.92, 0.95, 1.05, 1.22, 1.15])  # Mon..Sun

# Supply disruptions: (store code, sku, first day, last day) with zero sales.
STOCKOUTS = [
    ("MUM01", "SNB-003", dt.date(2026, 5, 11), dt.date(2026, 5, 24)),
    ("DEL02", "DRY-001", dt.date(2026, 7, 6), dt.date(2026, 7, 15)),
]


@dataclass
class Dataset:
    dates: np.ndarray  # (D,) datetime64[D]
    stores: list[StoreSpec]
    products: list[ProductSpec]
    units: np.ndarray  # (S, P, D) int
    discount: np.ndarray  # (P, D + PLANNED_WEEKS * 7) float, includes planned promos
    unit_cost: np.ndarray  # (P,) float
    on_hand: np.ndarray  # (S, P) int


def _bump(day_of_year: np.ndarray, center: float, width: float) -> np.ndarray:
    # Circular distance so a winter bump centred in January wraps around year end.
    dist = np.abs(day_of_year - center)
    dist = np.minimum(dist, 365 - dist)
    return np.exp(-0.5 * (dist / width) ** 2)


def _season(products: list[ProductSpec], dates: list[dt.date]) -> np.ndarray:
    doy = np.array([d.timetuple().tm_yday for d in dates], dtype=float)
    summer = _bump(doy, 135, 32)
    monsoon = _bump(doy, 215, 28)
    winter = _bump(doy, 10, 30)
    ordinals = np.array([d.toordinal() for d in dates], dtype=float)
    festive = np.zeros(len(dates))
    for diwali in DIWALI:
        # Demand peaks in the run-up to Diwali and drops off sharply after it.
        delta = ordinals - diwali.toordinal()
        width = np.where(delta < 0, 9.0, 2.5)
        festive = np.maximum(festive, np.exp(-0.5 * ((delta + 3) / width) ** 2))

    out = np.empty((len(products), len(dates)))
    for i, p in enumerate(products):
        out[i] = (
            1.0 + p.summer * summer + p.monsoon * monsoon + p.winter * winter + p.festive * festive
        )
    return out


def _promotions(products: list[ProductSpec], n_days: int, rng: np.random.Generator) -> np.ndarray:
    """Chain-wide 7-day promotions, roughly six per product per year."""
    discount = np.zeros((len(products), n_days))
    for i, p in enumerate(products):
        if p.category == "Festive & Gifting":
            continue
        n_promos = rng.integers(10, 14)
        starts = rng.choice(np.arange(0, n_days - 7, 7), size=n_promos, replace=False)
        for s in starts:
            discount[i, s : s + 7] = rng.choice([0.10, 0.15, 0.20, 0.25])
    return discount


def generate(
    stores: list[StoreSpec] | None = None,
    products: list[ProductSpec] | None = None,
    seed: int = 42,
) -> Dataset:
    stores = stores or STORES
    products = products or PRODUCTS
    rng = np.random.default_rng(seed)

    dates = [DATA_START + dt.timedelta(days=i) for i in range(WEEKS * 7)]
    n_days = len(dates)
    years_elapsed = np.arange(n_days) / 365.0
    weekday = WEEKDAY_FACTOR[[d.weekday() for d in dates]]

    season = _season(products, dates)
    calendar = _promotions(products, n_days + PLANNED_WEEKS * 7, rng)
    discount = calendar[:, :n_days]

    elasticity = np.array([CATEGORIES[p.category]["elasticity"] for p in products])
    promo_lift = (1 - discount) ** (-elasticity[:, None])
    # Customers stock up during promos, so the following week dips.
    was_promo = np.zeros_like(discount, dtype=bool)
    was_promo[:, 7:] = discount[:, :-7] > 0
    dip = np.array([CATEGORIES[p.category]["pantry_dip"] for p in products])
    post_promo = np.where(was_promo & (discount == 0), dip[:, None], 1.0)

    cat_trend = np.array([CATEGORIES[p.category]["trend"] for p in products])
    product_curve = (
        np.array([p.base_units for p in products])[:, None]
        * season
        * promo_lift
        * post_promo
        * (1 + cat_trend[:, None]) ** years_elapsed[None, :]
    )

    store_curve = np.empty((len(stores), n_days))
    competitor_day = (COMPETITOR_OPENS - DATA_START).days
    for j, s in enumerate(stores):
        curve = s.scale * (1 + s.annual_growth) ** years_elapsed
        if s.code == "PUN01":
            ramp = np.clip((np.arange(n_days) - competitor_day) / 21, 0, 1)
            curve = curve * (1 - 0.18 * ramp)
        store_curve[j] = curve

    lam = store_curve[:, None, :] * product_curve[None, :, :] * weekday[None, None, :]
    # Gamma-Poisson (negative binomial) noise: retail demand is over-dispersed.
    shape = 6.0
    lam = lam * rng.gamma(shape, 1 / shape, size=lam.shape)
    units = rng.poisson(lam).astype(np.int32)

    store_index = {s.code: j for j, s in enumerate(stores)}
    sku_index = {p.sku: i for i, p in enumerate(products)}
    for code, sku, first, last in STOCKOUTS:
        if code in store_index and sku in sku_index:
            a, b = (first - DATA_START).days, (last - DATA_START).days + 1
            units[store_index[code], sku_index[sku], a:b] = 0

    unit_cost = np.array(
        [round(p.price * CATEGORIES[p.category]["cost_ratio"], 2) for p in products]
    )

    # Inventory snapshot at the end of the data. Replenishment plans against upcoming
    # demand (so festive stock is built ahead of Diwali): most SKUs have ~4 weeks of
    # cover, a few are dangerously low and a few are overstocked.
    upcoming = [DATA_END + dt.timedelta(days=i + 1) for i in range(14)]
    upcoming_season = _season(products, upcoming).mean(axis=1)
    recent_season = season[:, -28:].mean(axis=1)
    recent_daily = units[:, :, -28:].mean(axis=2) + 0.05
    expected_daily = recent_daily * (upcoming_season / recent_season)[None, :]
    cover_days = rng.lognormal(np.log(28), 0.3, size=expected_daily.shape)
    roll = rng.random(expected_daily.shape)
    cover_days = np.where(roll < 0.06, rng.uniform(0.5, 4, expected_daily.shape), cover_days)
    cover_days = np.where(roll > 0.94, rng.uniform(70, 120, expected_daily.shape), cover_days)
    on_hand = np.round(expected_daily * cover_days).astype(np.int32)

    return Dataset(
        dates=np.array(dates, dtype="datetime64[D]"),
        stores=stores,
        products=products,
        units=units,
        discount=calendar,
        unit_cost=unit_cost,
        on_hand=on_hand,
    )
