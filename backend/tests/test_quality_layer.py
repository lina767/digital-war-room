"""Unit tests for agents.quality_layer."""

import math

import pytest

from agents.quality_layer import (
    detect_spread_conflict,
    fuse_numeric_observations,
    weighted_median,
)


def test_weighted_median_two_points_favors_higher_weight() -> None:
    # median position with cumulative weight: 0.9 vs 0.1 -> first sorted value wins at 0.5 mass
    v = weighted_median([70.0, 80.0], [0.9, 0.1])
    assert v == 70.0


def test_detect_spread_conflict() -> None:
    assert detect_spread_conflict([100.0, 100.5], relative_threshold=0.02) is None
    assert detect_spread_conflict([70.0, 85.0], relative_threshold=0.03) == "price_spread"


def test_fuse_two_curated_sources() -> None:
    fusion = fuse_numeric_observations(
        [
            {
                "value": 74.0,
                "source": "alpha_vantage",
                "fetched_at": "2026-03-21T12:00:00+00:00",
                "change_pct": "+1.0%",
                "as_of": "2026-03-20",
            },
            {
                "value": 74.2,
                "source": "fred",
                "fetched_at": "2026-03-21T12:00:00+00:00",
                "change_pct": "+0.9%",
                "as_of": "2026-03-19",
            },
        ]
    )
    assert fusion.corroboration >= 2
    assert fusion.conflict_flag is None
    assert 73.9 < fusion.value < 74.3


def test_fuse_empty_returns_nan() -> None:
    fusion = fuse_numeric_observations([])
    assert math.isnan(fusion.value)
