"""Weekly demand forecasting for every store x SKU series at once.

The model is deliberately simple and fully vectorised with numpy, so it runs in well
under a second on a 512 MB free-tier instance. It uses the two things retail planners
always know in advance:

* **Planned promotions.** Promo lift is learned per category as a price elasticity,
  removed from history, and re-applied to the future promo calendar.
* **Festival calendar.** Diwali moves by up to three weeks a year, so the weeks around
  it get their own event-aligned factors instead of a week-of-year factor.

What remains is deseasonalised with a per-category week-of-year index (pooling SKUs is
far less noisy than estimating per series) and smoothed with damped-trend Holt
exponential smoothing. 80% intervals come from one-step residuals.

``backtest`` scores the model against naive baselines on a held-out window using WAPE
(weighted absolute percentage error), the standard retail accuracy metric.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.services.calendar import EVENT_WINDOW, NO_EVENT

PERIOD = 52
Z_80 = 1.2816


@dataclass
class ForecastResult:
    mean: np.ndarray  # (S, H)
    lower: np.ndarray
    upper: np.ndarray


@dataclass
class Season:
    weekly: np.ndarray  # (G, PERIOD) week-of-year index
    event: np.ndarray  # (G, len(EVENT_WINDOW)) Diwali-aligned index

    def factors(self, groups: np.ndarray, weeks: np.ndarray, offsets: np.ndarray) -> np.ndarray:
        """Seasonal factor for each series (by group) at each absolute week number."""
        out = self.weekly[groups][:, weeks % PERIOD]
        in_event = offsets != NO_EVENT
        if in_event.any():
            cols = offsets[in_event] - EVENT_WINDOW.start
            out[:, in_event] = self.event[groups][:, cols]
        return out


def promo_elasticity(y: np.ndarray, discount: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Per-group elasticity e such that lift = (1 - discount) ** -e.

    Each promo week is compared with the average of nearby non-promo weeks, then a
    no-intercept regression of log(lift) on -log(1 - discount) gives e.
    """
    n_groups = int(groups.max()) + 1
    promo = discount > 0
    clean = np.where(promo, np.nan, y)
    # Baseline: mean of the 3 weeks either side, ignoring promo weeks.
    padded = np.pad(clean, ((0, 0), (3, 3)), constant_values=np.nan)
    windows = np.stack([padded[:, k : k + y.shape[1]] for k in range(7) if k != 3])
    with np.errstate(all="ignore"):
        baseline = np.nanmean(windows, axis=0)
        log_lift = np.log((y + 1) / (baseline + 1))
    x = -np.log(1 - np.clip(discount, 0, 0.9))
    usable = promo & np.isfinite(log_lift)
    elasticity = np.zeros(n_groups)
    for g in range(n_groups):
        m = usable & (groups == g)[:, None]
        if m.sum() >= 5:
            elasticity[g] = max(float((x[m] * log_lift[m]).sum() / (x[m] ** 2).sum()), 0.0)
    return elasticity


def _fill_circular(values: np.ndarray) -> np.ndarray:
    """Fill NaNs by linear interpolation around a circle."""
    if not np.isnan(values).any():
        return values
    n = len(values)
    known = np.flatnonzero(~np.isnan(values))
    if len(known) == 0:
        return np.ones(n)
    xs = np.concatenate([known - n, known, known + n])
    ys = np.tile(values[known], 3)
    return np.interp(np.arange(n), xs, ys)


def estimate_season(y: np.ndarray, groups: np.ndarray, offsets: np.ndarray) -> Season:
    n_groups = int(groups.max()) + 1
    t = np.arange(y.shape[1])
    in_event = offsets != NO_EVENT
    weekly = np.ones((n_groups, PERIOD))
    event = np.ones((n_groups, len(EVENT_WINDOW)))
    for g in range(n_groups):
        total = y[groups == g].sum(axis=0) + 1.0
        # Fit the trend on non-event weeks so the Diwali spike does not tilt it.
        slope, intercept = np.polyfit(t[~in_event], np.log(total[~in_event]), 1)
        ratio = total / np.exp(intercept + slope * t)

        pos = t[~in_event] % PERIOD
        sums = np.bincount(pos, weights=ratio[~in_event], minlength=PERIOD)
        counts = np.bincount(pos, minlength=PERIOD)
        raw = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
        raw = _fill_circular(raw)
        smooth = (np.roll(raw, 1) + 2 * raw + np.roll(raw, -1)) / 4
        weekly[g] = smooth / smooth.mean()

        for k, offset in enumerate(EVENT_WINDOW):
            hits = offsets == offset
            if hits.any():
                event[g, k] = float(np.mean(ratio[hits]))
    return Season(weekly=weekly, event=event)


def _holt_damped(
    d: np.ndarray, alpha: float, beta: float, phi: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    level = d[:, :4].mean(axis=1)
    trend = np.zeros(d.shape[0])
    residuals = np.zeros_like(d, dtype=float)
    for t in range(d.shape[1]):
        predicted = level + phi * trend
        residuals[:, t] = d[:, t] - predicted
        new_level = alpha * d[:, t] + (1 - alpha) * predicted
        trend = beta * (new_level - level) + (1 - beta) * phi * trend
        level = new_level
    return level, trend, residuals


def forecast(
    y: np.ndarray,
    groups: np.ndarray,
    horizon: int,
    *,
    offsets: np.ndarray | None = None,
    discount: np.ndarray | None = None,
    alpha: float = 0.2,
    beta: float = 0.03,
    phi: float = 0.9,
) -> ForecastResult:
    """Forecast ``horizon`` weeks for each row of ``y`` (shape (S, T)).

    ``offsets`` (T + H,) holds each week's Diwali offset (or NO_EVENT) and
    ``discount`` (S, T + H) the known promo discount per series and week; both cover
    history and the forecast horizon.
    """
    n_series, n_weeks = y.shape
    total_weeks = n_weeks + horizon
    if offsets is None:
        offsets = np.full(total_weeks, NO_EVENT)
    if discount is None:
        discount = np.zeros((n_series, total_weeks))

    elasticity = promo_elasticity(y, discount[:, :n_weeks], groups)
    lift = (1 - discount) ** (-elasticity[groups][:, None])
    base_y = y / lift[:, :n_weeks]

    season = estimate_season(base_y, groups, offsets[:n_weeks])
    all_weeks = np.arange(total_weeks)
    factors = season.factors(groups, all_weeks, offsets)
    deseasonalised = base_y / factors[:, :n_weeks]

    level, trend, residuals = _holt_damped(deseasonalised, alpha, beta, phi)

    steps = np.arange(1, horizon + 1)
    damping = np.cumsum(phi**steps)
    future = factors[:, n_weeks:] * lift[:, n_weeks:]
    base = np.maximum(level[:, None] + trend[:, None] * damping[None, :], 0)
    mean = base * future

    sigma = residuals[:, -26:].std(axis=1)
    spread = Z_80 * sigma[:, None] * np.sqrt(steps)[None, :] * future
    return ForecastResult(mean=mean, lower=np.maximum(mean - spread, 0), upper=mean + spread)


def wape(actual: np.ndarray, predicted: np.ndarray) -> float:
    total = float(np.abs(actual).sum())
    return float(np.abs(actual - predicted).sum() / total) if total else 0.0


def backtest(
    y: np.ndarray,
    groups: np.ndarray,
    holdout: int = 12,
    *,
    offsets: np.ndarray | None = None,
    discount: np.ndarray | None = None,
) -> dict[str, float | None]:
    """Train on all but the last ``holdout`` weeks and score the model and baselines.

    ``offsets``/``discount`` cover exactly the weeks of ``y``: the promo calendar and
    festival dates for the holdout are known in advance, so the model may use them.
    """
    n_weeks = y.shape[1]
    n_train = n_weeks - holdout
    train, test = y[:, :n_train], y[:, n_train:]

    model = forecast(
        train,
        groups,
        holdout,
        offsets=None if offsets is None else offsets[:n_weeks],
        discount=None if discount is None else discount[:, :n_weeks],
    ).mean
    naive = np.repeat(train[:, -1:], holdout, axis=1)
    moving_avg = np.repeat(train[:, -4:].mean(axis=1, keepdims=True), holdout, axis=1)

    seasonal_naive: float | None = None
    if n_train >= PERIOD:
        idx = n_train + np.arange(holdout) - PERIOD
        seasonal_naive = wape(test, y[:, idx])

    return {
        "model": wape(test, model),
        "naive": wape(test, naive),
        "seasonal_naive": seasonal_naive,
        "moving_avg": wape(test, moving_avg),
    }
