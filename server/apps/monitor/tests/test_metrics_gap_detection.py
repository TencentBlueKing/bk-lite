from types import SimpleNamespace

import pytest

from apps.monitor.services.metrics import Metrics
from apps.monitor.views.metrics_instance import MetricsInstanceViewSet


pytestmark = pytest.mark.unit


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
        }
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
        ("cpu_usage", 0.0, 600.0, "1h"),
        ("cpu_usage", 0.0, 600.0, "60s"),
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

    assert calls == [("cpu_usage", 0.0, 600.0, "60s")]
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

    assert calls == [("cpu_usage", 0.0, 600.0, "1h")]
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
        ("cpu_usage", 0.0, 2592000.0, "1h"),
        ("cpu_usage", 0.0, 2592000.0, "60s"),
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
    ):
        captured.update(
            {
                "query": query,
                "start": start,
                "end": end,
                "step": step,
                "detect_gaps": detect_gaps,
                "collection_interval_seconds": collection_interval_seconds,
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
    }
