import datetime as dt

import numpy as np

from app.services import forecasting, synthetic
from app.services.calendar import NO_EVENT, diwali_offsets


def weekly(data: synthetic.Dataset) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    s, p, d = data.units.shape
    y = data.units.reshape(s, p, d // 7, 7).sum(-1).reshape(s * p, -1).astype(float)
    categories = sorted({prod.category for prod in data.products})
    groups = np.array([categories.index(prod.category) for prod in data.products] * s)
    discount = np.tile(data.discount.reshape(p, -1, 7).mean(-1), (s, 1))
    return y, groups, discount


def test_beats_every_baseline_on_synthetic_data() -> None:
    y, groups, discount = weekly(synthetic.generate())
    weeks = [synthetic.DATA_START + dt.timedelta(weeks=i) for i in range(y.shape[1])]
    offsets = np.array(diwali_offsets(weeks))

    scores = forecasting.backtest(
        y, groups, holdout=12, offsets=offsets, discount=discount[:, : y.shape[1]]
    )

    baselines = [scores["naive"], scores["seasonal_naive"], scores["moving_avg"]]
    assert scores["model"] < min(b for b in baselines if b is not None)


def test_recovers_promo_elasticity() -> None:
    y, groups, discount = weekly(synthetic.generate())
    categories = sorted(synthetic.CATEGORIES)
    estimated = forecasting.promo_elasticity(y, discount[:, : y.shape[1]], groups)
    for i, name in enumerate(categories):
        true = synthetic.CATEGORIES[name]["elasticity"]
        if name != "Festive & Gifting":  # never promoted
            assert abs(estimated[i] - true) < 0.35, name


def test_forecast_is_non_negative_with_ordered_interval() -> None:
    rng = np.random.default_rng(0)
    t = np.arange(104)
    y = rng.poisson(50 + 30 * np.sin(2 * np.pi * t / 52), size=(5, 104)).astype(float)
    result = forecasting.forecast(y, np.zeros(5, dtype=int), horizon=8)
    assert result.mean.shape == (5, 8)
    assert (result.lower >= 0).all()
    assert (result.lower <= result.mean).all() and (result.mean <= result.upper).all()


def test_seasonal_index_has_unit_mean() -> None:
    y = np.random.default_rng(1).poisson(20, size=(4, 104)).astype(float)
    season = forecasting.estimate_season(y, np.array([0, 0, 1, 1]), np.full(104, NO_EVENT))
    assert np.allclose(season.weekly.mean(axis=1), 1.0)


def test_wape() -> None:
    assert forecasting.wape(np.array([10.0, 10.0]), np.array([5.0, 15.0])) == 0.5
    assert forecasting.wape(np.zeros(3), np.ones(3)) == 0.0


def test_diwali_offsets_follow_the_festival() -> None:
    weeks = [dt.date(2025, 9, 29) + dt.timedelta(weeks=i) for i in range(6)]
    # Diwali 2025 is Monday 20 Oct, so that week is offset 0.
    assert diwali_offsets(weeks) == [-3, -2, -1, 0, 1, NO_EVENT]
