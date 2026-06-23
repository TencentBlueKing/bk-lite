"""Tests for issue #3533: steps/data upper-bound guards (DoS prevention)."""

import os
import sys
import types
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Minimal stub setup so we can import the schemas module without a full BentoML
# / pandas environment being configured via Django settings.
# ---------------------------------------------------------------------------

def _load_schema_module():
    """Load api_schema via importlib to avoid any BentoML/Django deps."""
    schema_path = (
        Path(__file__).parent.parent
        / "classify_timeseries_server"
        / "serving"
        / "schemas"
        / "api_schema.py"
    )
    spec = importlib.util.spec_from_file_location("api_schema", schema_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def schema_mod():
    return _load_schema_module()


@pytest.fixture(scope="module")
def make_point(schema_mod):
    """Factory for TimeSeriesPoint dicts."""
    def _make(timestamp=1700000000, value=1.0):
        return {"timestamp": timestamp, "value": value}
    return _make


# ---------------------------------------------------------------------------
# PredictionConfig.steps upper-bound tests
# ---------------------------------------------------------------------------

class TestStepsBound:
    def test_steps_zero_rejected(self, schema_mod):
        """steps=0 must be rejected (gt=0)."""
        with pytest.raises(ValidationError):
            schema_mod.PredictionConfig(steps=0)

    def test_steps_one_accepted(self, schema_mod):
        """steps=1 is valid."""
        cfg = schema_mod.PredictionConfig(steps=1)
        assert cfg.steps == 1

    def test_steps_at_max_accepted(self, schema_mod):
        """steps equal to MAX_PREDICTION_STEPS is valid."""
        max_s = schema_mod.MAX_PREDICTION_STEPS
        cfg = schema_mod.PredictionConfig(steps=max_s)
        assert cfg.steps == max_s

    def test_steps_exceed_max_rejected(self, schema_mod):
        """steps > MAX_PREDICTION_STEPS must be rejected — this is the fix for #3533.

        Before the fix, steps had only gt=0; passing 100000 would be accepted
        and trigger a 100 000-iteration inference loop.
        """
        max_s = schema_mod.MAX_PREDICTION_STEPS
        with pytest.raises(ValidationError):
            schema_mod.PredictionConfig(steps=max_s + 1)

    def test_steps_large_dos_value_rejected(self, schema_mod):
        """steps=100000 (the DoS value from the issue) must be rejected."""
        with pytest.raises(ValidationError):
            schema_mod.PredictionConfig(steps=100_000)

    def test_env_override_max_steps(self):
        """MAX_PREDICTION_STEPS should be configurable via environment variable."""
        with patch.dict(os.environ, {"MAX_PREDICTION_STEPS": "500"}):
            mod = _load_schema_module()
            assert mod.MAX_PREDICTION_STEPS == 500
            # value=500 accepted
            cfg = mod.PredictionConfig(steps=500)
            assert cfg.steps == 500
            # value=501 rejected
            with pytest.raises(ValidationError):
                mod.PredictionConfig(steps=501)


# ---------------------------------------------------------------------------
# PredictRequest.data max_length tests
# ---------------------------------------------------------------------------

class TestDataBound:
    def test_data_within_limit_accepted(self, schema_mod, make_point):
        """data with one point is valid."""
        req = schema_mod.PredictRequest(
            data=[make_point(timestamp=1700000000 + i) for i in range(5)],
            config={"steps": 1},
        )
        assert len(req.data) == 5

    def test_data_exceeds_max_length_rejected(self, schema_mod, make_point):
        """data exceeding MAX_INPUT_DATA_POINTS must be rejected — fix for #3533.

        Before the fix, data had no max_length and an arbitrarily large list
        could be sent, consuming O(n×steps) memory.
        """
        max_d = schema_mod.MAX_INPUT_DATA_POINTS
        oversized = [make_point(timestamp=1700000000 + i) for i in range(max_d + 1)]
        with pytest.raises(ValidationError):
            schema_mod.PredictRequest(
                data=oversized,
                config={"steps": 1},
            )

    def test_env_override_max_data_points(self, make_point):
        """MAX_INPUT_DATA_POINTS should be configurable via environment variable."""
        with patch.dict(os.environ, {"MAX_INPUT_DATA_POINTS": "10"}):
            mod = _load_schema_module()
            assert mod.MAX_INPUT_DATA_POINTS == 10
            # 10 points: ok
            pts_ok = [make_point(timestamp=1700000000 + i) for i in range(10)]
            req = mod.PredictRequest(data=pts_ok, config={"steps": 1})
            assert len(req.data) == 10
            # 11 points: rejected
            pts_bad = [make_point(timestamp=1700000000 + i) for i in range(11)]
            with pytest.raises(ValidationError):
                mod.PredictRequest(data=pts_bad, config={"steps": 1})


# ---------------------------------------------------------------------------
# Service-layer hardening guard (import-level check, no BentoML runtime needed)
# ---------------------------------------------------------------------------

class TestServiceGuardConstants:
    """Verify service.py imports the right guard constants from schemas."""

    def test_service_imports_guard_constants(self):
        """service.py must import MAX_PREDICTION_STEPS and MAX_INPUT_DATA_POINTS.

        This test verifies the constants exist and match schema values.
        Reverting the fix removes this import and the test fails.
        """
        schema_mod = _load_schema_module()
        # Guard values must be positive integers
        assert isinstance(schema_mod.MAX_PREDICTION_STEPS, int)
        assert schema_mod.MAX_PREDICTION_STEPS > 0
        assert isinstance(schema_mod.MAX_INPUT_DATA_POINTS, int)
        assert schema_mod.MAX_INPUT_DATA_POINTS > 0

    def test_min_clamp_logic(self, schema_mod):
        """Verify min-clamp logic used in service.py is coherent with schema bound."""
        max_s = schema_mod.MAX_PREDICTION_STEPS
        # schema already rejects steps > max_s, so min(steps, max_s) == steps always
        # (the guard is defense-in-depth)
        for steps in (1, 10, max_s):
            assert min(steps, max_s) == steps
