import json
from types import SimpleNamespace

import pytest

from apps.monitor.services.metrics import Metrics, MetricsQueryBudgetExceeded
from apps.monitor.views.metrics_instance import MetricsInstanceViewSet

pytestmark = pytest.mark.unit


def test_default_range_budget_rejects_excessive_grid_before_vm_query(monkeypatch):
    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            raise AssertionError("超限请求不应访问 VictoriaMetrics")

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    with pytest.raises(MetricsQueryBudgetExceeded) as raised:
        Metrics.get_metrics_range(
            "cpu_usage",
            0,
            30 * 24 * 60 * 60 * 1000,
            "1s",
        )

    assert raised.value.STATUS_CODE == 422
    assert raised.value.data["code"] == "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED"
    assert raised.value.data["reason"] == "points_per_series"


def test_default_range_budget_rejects_excessive_series_before_fill(monkeypatch):
    monkeypatch.setattr(Metrics, "RANGE_QUERY_MAX_SERIES", 2, raising=False)

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            assert query == "limitk(3, cpu_usage)"
            return {
                "status": "success",
                "data": {"result": [{"metric": {"id": str(index)}, "values": [[0, "1"]]} for index in range(3)]},
            }

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    with pytest.raises(MetricsQueryBudgetExceeded) as raised:
        Metrics.get_metrics_range("cpu_usage", 0, 60000, "60s")

    assert raised.value.data["reason"] == "series"
    assert raised.value.data["actual"]["series"] == 3


def test_default_range_budget_keeps_explicit_series_limit_within_cap(monkeypatch):
    monkeypatch.setattr(Metrics, "RANGE_QUERY_MAX_SERIES", 2)
    calls = []

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            calls.append((query, start, end, step))
            return {
                "status": "success",
                "data": {
                    "result": [
                        {"metric": {"id": "1"}, "values": [[0, "1"]]},
                        {"metric": {"id": "2"}, "values": [[0, "2"]]},
                    ]
                },
            }

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    Metrics.get_metrics_range("topk(2, cpu_usage)", 0, 60000, "60s", fill_missing=False)

    assert calls == [("topk(2, cpu_usage)", 0.0, 60.0, "60s")]


def test_default_range_budget_rejects_total_grid_before_fill(monkeypatch):
    monkeypatch.setattr(Metrics, "RANGE_QUERY_MAX_SERIES", 10, raising=False)
    monkeypatch.setattr(Metrics, "RANGE_QUERY_MAX_TOTAL_POINTS", 5, raising=False)

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            return {
                "status": "success",
                "data": {
                    "result": [
                        {"metric": {"id": "1"}, "values": [[0, "1"]]},
                        {"metric": {"id": "2"}, "values": [[0, "1"]]},
                    ]
                },
            }

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)
    fill_called = False

    def fail_if_fill_runs(*args, **kwargs):
        nonlocal fill_called
        fill_called = True

    monkeypatch.setattr(Metrics, "fill_missing_points", staticmethod(fail_if_fill_runs))

    with pytest.raises(MetricsQueryBudgetExceeded) as raised:
        Metrics.get_metrics_range("cpu_usage", 0, 120000, "60s")

    assert raised.value.data["reason"] == "total_points"
    assert raised.value.data["actual"]["total_points"] == 6
    assert fill_called is False


def test_fill_missing_points_rejects_excessive_grid_before_dataframe_allocation(monkeypatch):
    monkeypatch.setattr(Metrics, "RANGE_QUERY_MAX_TOTAL_POINTS", 5)
    data = [
        {"metric": {"id": "1"}, "values": [[0, "1"]]},
        {"metric": {"id": "2"}, "values": [[0, "1"]]},
    ]

    with pytest.raises(MetricsQueryBudgetExceeded) as raised:
        Metrics.fill_missing_points(0, 120, 60, data)

    assert raised.value.data["reason"] == "total_points"
    assert data[0]["values"] == [[0, "1"]]


def test_metrics_range_view_returns_structured_422_for_budget_error(monkeypatch):
    error = MetricsQueryBudgetExceeded(
        data={
            "code": "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED",
            "reason": "points_per_series",
            "limits": {"points_per_series": 10000},
            "actual": {"points_per_series": 20000},
        }
    )
    monkeypatch.setattr(
        "apps.monitor.views.metrics_instance.MetricsService.get_metrics_range",
        lambda *args, **kwargs: (_ for _ in ()).throw(error),
    )

    response = MetricsInstanceViewSet().get_metrics_range(
        SimpleNamespace(
            GET={
                "query": "cpu_usage",
                "start": "0",
                "end": "1200000",
                "step": "60s",
            }
        )
    )

    assert response.status_code == 422
    assert json.loads(response.content) == {
        "data": error.data,
        "result": False,
        "message": "指标范围查询超过服务端预算，请缩短时间范围、减少实例或增大查询步长",
    }


def test_card_budget_clamps_step_before_shared_hard_budget(monkeypatch):
    calls = []

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            calls.append((query, start, end, step))
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "host-1"},
                            "values": [[0, "1"], [600, "2"]],
                        }
                    ]
                },
            }

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    response = Metrics.get_metrics_range(
        "cpu_usage",
        0,
        600000,
        "1s",
        card_budget=True,
    )

    assert calls == [("limitk(201, cpu_usage)", 0.0, 600.0, "2s")]
    assert response["data"]["step"] == "2s"
    assert response["data"]["step_clamped"] is True
    assert response["data"]["series_budget"] == {
        "truncated": False,
        "limit": 200,
        "applied": True,
    }


def test_detect_gap_intervals_finds_missing_samples_inside_coarse_step():
    series = [
        {
            "metric": {"instance_id": "host-1", "__name__": "cpu_usage"},
            "values": [
                [0, "1"],
                [60, "1"],
                [120, "1"],
                [480, "1"],
                [540, "1"],
            ],
        }
    ]

    gaps = Metrics.detect_gap_intervals(series, collection_interval_seconds=60)

    assert gaps == [
        {
            "start": 180.0,
            "end": 420.0,
            "duration": 300.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1", "__name__": "cpu_usage"},
                    "missing_points": 5,
                }
            ],
        }
    ]


def test_detect_gap_intervals_skips_invalid_collection_interval():
    series = [
        {
            "metric": {"instance_id": "host-1"},
            "values": [[0, "1"], [300, "1"]],
        }
    ]

    assert Metrics.detect_gap_intervals(series, collection_interval_seconds="") == []


def test_detect_gap_intervals_returns_empty_when_samples_are_continuous():
    series = [
        {
            "metric": {"instance_id": "host-1"},
            "values": [[0, "1"], [60, "1"], [120, "1"], [180, "1"]],
        }
    ]

    assert Metrics.detect_gap_intervals(series, collection_interval_seconds=60) == []


def test_detect_gap_intervals_keeps_overlapping_series_gaps_independent():
    series = [
        {
            "metric": {"instance_id": "host-1", "cpu": "0"},
            "values": [[0, "1"], [60, "1"], [120, "1"], [480, "1"]],
        },
        {
            "metric": {"instance_id": "host-1", "cpu": "1"},
            "values": [[0, "1"], [60, "1"], [240, "1"], [600, "1"]],
        },
    ]

    gaps = Metrics.detect_gap_intervals(series, collection_interval_seconds=60)

    assert gaps == [
        {
            "start": 120.0,
            "end": 180.0,
            "duration": 120.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1", "cpu": "1"},
                    "missing_points": 2,
                }
            ],
        },
        {
            "start": 180.0,
            "end": 420.0,
            "duration": 300.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1", "cpu": "0"},
                    "missing_points": 5,
                }
            ],
        },
        {
            "start": 300.0,
            "end": 540.0,
            "duration": 300.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1", "cpu": "1"},
                    "missing_points": 5,
                },
            ],
        },
    ]


def test_merge_gap_intervals_keeps_adjacent_different_series_gaps_independent():
    gaps = Metrics.merge_gap_intervals(
        [
            {"start": 120.0, "end": 180.0, "duration": 120.0, "series": [{"metric": {"cpu": "0"}}]},
            {"start": 240.0, "end": 300.0, "duration": 120.0, "series": [{"metric": {"cpu": "1"}}]},
        ],
        collection_interval_seconds=60,
    )

    assert gaps == [
        {
            "start": 120.0,
            "end": 180.0,
            "duration": 120.0,
            "series": [{"metric": {"cpu": "0"}}],
        },
        {
            "start": 240.0,
            "end": 300.0,
            "duration": 120.0,
            "series": [{"metric": {"cpu": "1"}}],
        },
    ]


def test_merge_gap_intervals_combines_adjacent_gaps_for_same_series():
    gaps = Metrics.merge_gap_intervals(
        [
            {
                "start": 120.0,
                "end": 180.0,
                "duration": 120.0,
                "series": [{"metric": {"cpu": "0"}, "missing_points": 2}],
            },
            {
                "start": 240.0,
                "end": 300.0,
                "duration": 120.0,
                "series": [{"metric": {"cpu": "0"}, "missing_points": 2}],
            },
        ],
        collection_interval_seconds=60,
    )

    assert gaps == [
        {
            "start": 120.0,
            "end": 300.0,
            "duration": 240.0,
            "series": [{"metric": {"cpu": "0"}, "missing_points": 4}],
        }
    ]


def test_get_metrics_range_adds_gap_metadata_when_detection_enabled(monkeypatch):
    calls = []

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            calls.append((query, start, end, step))
            if step == "60s":
                return {
                    "status": "success",
                    "data": {
                        "result": [
                            {
                                "metric": {"instance_id": "host-1"},
                                "values": [[0, "1"], [60, "1"], [120, "1"], [480, "1"]],
                            }
                        ]
                    },
                }
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "host-1"},
                            "values": [[0, "1"], [3600, "1"]],
                        }
                    ]
                },
            }

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    response = Metrics.get_metrics_range(
        "cpu_usage",
        0,
        600000,
        "1h",
        detect_gaps=True,
        collection_interval_seconds=60,
    )

    assert calls == [
        ("limitk(2001, cpu_usage)", 0.0, 600.0, "1h"),
        ("limitk(2001, cpu_usage)", 0.0, 600.0, "60s"),
    ]
    assert response["data"]["gap_detection"] == {"status": "ok", "limited": False}
    assert response["data"]["gaps"] == [
        {
            "start": 180.0,
            "end": 420.0,
            "duration": 300.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1"},
                    "missing_points": 5,
                }
            ],
        },
        {
            "start": 540.0,
            "end": 600.0,
            "duration": 120.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1"},
                    "missing_points": 2,
                }
            ],
        },
    ]


def test_get_metrics_range_marks_trailing_gap_until_selected_range_end(monkeypatch):
    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "host-1"},
                            "values": [[0, "1"], [60, "1"], [120, "1"]],
                        }
                    ]
                },
            }

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    response = Metrics.get_metrics_range(
        "cpu_usage",
        0,
        1800000,
        "60s",
        detect_gaps=True,
        collection_interval_seconds=60,
    )

    assert response["data"]["gaps"] == [
        {
            "start": 180.0,
            "end": 1800.0,
            "duration": 1680.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1"},
                    "missing_points": 28,
                }
            ],
        }
    ]


def test_get_metrics_range_marks_leading_gap_from_selected_range_start(monkeypatch):
    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "host-1"},
                            "values": [[600, "1"], [660, "1"], [720, "1"]],
                        }
                    ]
                },
            }

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    response = Metrics.get_metrics_range(
        "cpu_usage",
        0,
        900000,
        "60s",
        detect_gaps=True,
        collection_interval_seconds=60,
    )

    assert response["data"]["gaps"] == [
        {
            "start": 0.0,
            "end": 540.0,
            "duration": 600.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1"},
                    "missing_points": 10,
                }
            ],
        },
        {
            "start": 780.0,
            "end": 900.0,
            "duration": 180.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1"},
                    "missing_points": 3,
                }
            ],
        },
    ]


def test_get_metrics_range_reuses_response_when_step_matches_collection_interval(monkeypatch):
    calls = []

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            calls.append((query, start, end, step))
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "host-1"},
                            "values": [[0, "1"], [60, "1"], [120, "1"], [480, "1"]],
                        }
                    ]
                },
            }

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    response = Metrics.get_metrics_range(
        "cpu_usage",
        0,
        600000,
        "60s",
        detect_gaps=True,
        collection_interval_seconds=60,
    )

    assert calls == [("limitk(2001, cpu_usage)", 0.0, 600.0, "60s")]
    assert response["data"]["gap_detection"] == {"status": "ok", "limited": False}
    assert response["data"]["gaps"] == [
        {
            "start": 180.0,
            "end": 420.0,
            "duration": 300.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1"},
                    "missing_points": 5,
                }
            ],
        },
        {
            "start": 540.0,
            "end": 600.0,
            "duration": 120.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1"},
                    "missing_points": 2,
                }
            ],
        },
    ]


def test_get_metrics_range_limits_gap_detection_when_query_would_be_too_large(monkeypatch):
    calls = []

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            calls.append((query, start, end, step))
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "host-1"},
                            "values": [[0, "1"], [3600, "1"]],
                        }
                    ]
                },
            }

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    response = Metrics.get_metrics_range(
        "cpu_usage",
        0,
        600000,
        "1h",
        detect_gaps=True,
        collection_interval_seconds=60,
        max_gap_detection_points=3,
    )

    assert calls == [("limitk(2001, cpu_usage)", 0.0, 600.0, "1h")]
    assert response["data"]["gaps"] == []
    assert response["data"]["gap_detection"] == {
        "status": "limited",
        "limited": True,
        "reason": "max_points_exceeded",
    }


def test_get_metrics_range_detects_one_minute_gaps_for_thirty_day_window(monkeypatch):
    calls = []
    thirty_days_ms = 30 * 24 * 60 * 60 * 1000

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            calls.append((query, start, end, step))
            if step == "60s":
                return {
                    "status": "success",
                    "data": {
                        "result": [
                            {
                                "metric": {"instance_id": "host-1"},
                                "values": [[0, "1"], [60, "1"], [120, "1"], [480, "1"]],
                            }
                        ]
                    },
                }
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "host-1"},
                            "values": [[0, "1"], [3600, "1"]],
                        }
                    ]
                },
            }

    monkeypatch.setattr("apps.monitor.services.metrics.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    response = Metrics.get_metrics_range(
        "cpu_usage",
        0,
        thirty_days_ms,
        "1h",
        detect_gaps=True,
        collection_interval_seconds=60,
    )

    assert calls == [
        ("limitk(2001, cpu_usage)", 0.0, 2592000.0, "1h"),
        ("limitk(2001, cpu_usage)", 0.0, 2592000.0, "60s"),
    ]
    assert response["data"]["gap_detection"] == {"status": "ok", "limited": False}
    assert response["data"]["gaps"] == [
        {
            "start": 180.0,
            "end": 420.0,
            "duration": 300.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1"},
                    "missing_points": 5,
                }
            ],
        },
        {
            "start": 540.0,
            "end": 2592000.0,
            "duration": 2591520.0,
            "series": [
                {
                    "metric": {"instance_id": "host-1"},
                    "missing_points": 43192,
                }
            ],
        },
    ]


def test_metrics_range_view_passes_gap_detection_query_params(monkeypatch):
    captured = {}

    def fake_get_metrics_range(
        query,
        start,
        end,
        step,
        detect_gaps=False,
        collection_interval_seconds=None,
        card_budget=False,
    ):
        captured.update(
            {
                "query": query,
                "start": start,
                "end": end,
                "step": step,
                "detect_gaps": detect_gaps,
                "collection_interval_seconds": collection_interval_seconds,
                "card_budget": card_budget,
            }
        )
        return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr(
        "apps.monitor.views.metrics_instance.MetricsService.get_metrics_range",
        fake_get_metrics_range,
    )
    monkeypatch.setattr(
        "apps.monitor.views.metrics_instance.WebUtils.response_success",
        staticmethod(lambda data: data),
    )

    response = MetricsInstanceViewSet().get_metrics_range(
        SimpleNamespace(
            GET={
                "query": "cpu_usage",
                "start": "0",
                "end": "600000",
                "step": "1h",
                "detect_gaps": "true",
                "collection_interval": "60",
            }
        )
    )

    assert response == {"status": "success", "data": {"result": []}}
    assert captured == {
        "query": "cpu_usage",
        "start": "0",
        "end": "600000",
        "step": "1h",
        "detect_gaps": True,
        "collection_interval_seconds": "60",
        "card_budget": False,
    }
