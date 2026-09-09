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
        (WindowType.SLIDING, "f385d1f7127142f53d1853066f34da6bd244e4ef36ba25531d8a5e5e60c3f959"),
        (WindowType.SESSION, "ff5ce8a85a269378fbd15c36015cbd94bd77f8f3535e66621bd85c684008a3f5"),
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


def test_sql_builder_resolves_enrichment_dimension_to_safe_json_expression(monkeypatch):
    monkeypatch.setattr(
        WindowConfig,
        "get_window_start",
        lambda self: datetime.fromisoformat("2026-08-05T08:00:00+00:00"),
    )
    sql = SQLBuilder().build_aggregation_sql(
        dimensions=["enrichment.cmdb.owner"],
        window_config=WindowConfig(WindowType.SLIDING, window_size_minutes=10),
        strategy_id=42,
    )

    assert "json_extract_string(enrichment, '$.cmdb.owner')" in sql
    assert "enrichment.cmdb.owner=" in sql
