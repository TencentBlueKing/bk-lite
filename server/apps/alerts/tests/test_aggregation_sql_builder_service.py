import hashlib
from datetime import datetime

import pytest

from apps.alerts.aggregation.query.builder import SQLBuilder
from apps.alerts.aggregation.window.factory import WindowConfig, WindowType


UNSAFE_DEFAULT_GLOBALS = {"lipsum", "cycler", "joiner", "namespace"}
pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("window_type", "expected_sha256"),
    (
        (WindowType.SLIDING, "890b2a27a22a1dcaa76f9836e9c403526eb5ba8930ec48d71e1da2e79c151236"),
        (WindowType.SESSION, "a476dbd96e85ac0ac159ca35647effeceb65e30086dbb733893e20a955a965e2"),
    ),
)
def test_sql_builder_output_matches_ordinary_environment_baseline(monkeypatch, window_type, expected_sha256):
    monkeypatch.setattr(
        WindowConfig,
        "get_window_start",
        lambda self: datetime.fromisoformat("2026-08-05T08:00:00+00:00"),
    )
    monkeypatch.setattr(
        WindowConfig,
        "get_session_end_time",
        lambda self: datetime.fromisoformat("2026-08-05T09:00:00+00:00"),
    )
    builder = SQLBuilder()
    sql = builder.build_aggregation_sql(
        dimensions=["resource_id", "item"],
        window_config=WindowConfig(window_type, window_size_minutes=10, session_timeout_minutes=60),
        strategy_id=42,
    )

    assert hashlib.sha256(sql.encode()).hexdigest() == expected_sha256


def test_sql_builder_environment_has_no_default_globals():
    assert UNSAFE_DEFAULT_GLOBALS.isdisjoint(SQLBuilder().env.globals)
