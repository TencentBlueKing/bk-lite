import threading
import time

import pytest
import yaml

from apps.opspilot.metis.llm.tools.mlops.monitor_store import latest_monitor_metric_query, record_monitor_metric_query
from apps.opspilot.metis.llm.tools.mlops.predict import get_mlops_serving_prompt, mlops_predict_timeseries, mlops_predict_timeseries_impl, run_bounded
from apps.opspilot.metis.llm.tools.mlops.reshape import choose_frequency, normalize_timestamp, prepare_series
from apps.opspilot.services.builtin_tools import BUILTIN_MLOPS_TOOL_ID, build_builtin_mlops_tool

REPO_ROOT_LANG = "apps/opspilot/language"


def test_normalize_timestamp_converts_milliseconds():
    assert normalize_timestamp(1_700_000_000_000) == 1_700_000_000
    assert normalize_timestamp(1_700_000_000) == 1_700_000_000
    assert normalize_timestamp(10**12) == 10**12
    assert normalize_timestamp(10**12 + 1) == (10**12 + 1) // 1000


def test_frequency_for_two_days_is_fifteen_minutes():
    frequency, steps, label = choose_frequency(2)
    assert (frequency, steps, label) == (900, 192, "15m")


def test_frequency_for_seven_days_is_hourly():
    frequency, steps, label = choose_frequency(7)
    assert (frequency, steps, label) == (3600, 168, "1h")


def test_frequency_for_thirty_days_is_two_hours():
    frequency, steps, label = choose_frequency(30)
    assert (frequency, steps, label) == (7200, 360, "2h")


def test_longer_horizon_caps_steps():
    _frequency, steps, _label = choose_frequency(400)
    assert steps <= 500


def test_prepare_series_keeps_recent_continuous_segment_across_one_gap():
    start = 1_700_000_000
    start -= start % 900
    points = []
    for index in range(30):
        if index == 3:
            continue
        points.append({"timestamp": start + index * 900, "value": index})
    prepared = prepare_series(points, 1 / 24)
    assert prepared["ok"] is True
    assert prepared["steps"] == 4
    assert len(prepared["data"]) >= 8
    assert prepared["data"][-1]["value"] == 29


def test_prepare_series_keeps_last_value_in_bucket_and_caps_history():
    start = 1_700_000_000
    start -= start % 900
    points = []
    for index in range(500):
        points.append({"timestamp": start + index * 900, "value": index})
        points.append({"timestamp": start + index * 900 + 100, "value": index + 0.5})
    prepared = prepare_series(points, 1)
    assert prepared["ok"] is True
    assert prepared["steps"] == 96
    assert len(prepared["data"]) == 96 * 4
    assert prepared["data"][-1]["value"] == 499.5


def test_prepare_series_names_the_gap_when_recent_history_is_short():
    start = 1_700_000_000
    start -= start % 900
    points = [{"timestamp": start + index * 900, "value": index} for index in range(5)]
    points.append({"timestamp": start + 40 * 900, "value": 40})
    prepared = prepare_series(points, 1)
    assert prepared["ok"] is False
    assert "至少需要" in prepared["error"]
    assert "缺口在" in prepared["error"]


def test_prepare_series_rejects_short_continuous_history():
    start = 1_700_000_000
    prepared = prepare_series(
        [{"timestamp": start, "value": 1}, {"timestamp": start + 900, "value": 2}],
        1 / 24,
    )
    assert prepared["ok"] is False
    assert "至少需要" in prepared["error"]


def _config(serving_ids="[7]", execution_id="exec-1"):
    return {
        "configurable": {
            "execution_id": execution_id,
            "serving_ids": serving_ids,
            "timezone": "Asia/Shanghai",
            "caller_identity": {
                "username": "alice",
                "domain": "domain.com",
                "team_id": 1,
                "include_children": False,
            },
        }
    }


def _hourly_points(count, start=1_700_000_000, scale=1):
    start -= start % 3600
    return [{"timestamp": (start + index * 3600) * 1000, "value": (index + 1) * scale} for index in range(count)]


def _monitor_payload(series):
    return {
        "success": True,
        "data": {
            "data": {
                "result": [{"metric": labels, "values": [[point["timestamp"], point["value"]] for point in points]} for labels, points in series]
            }
        },
    }


@pytest.fixture
def names(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.mlops.predict._serving_names",
        lambda serving_ids: {item: f"serving-{item}" for item in serving_ids},
    )


def _ok_predict(body_value):
    def _call(serving_id, data, steps, actor_context):
        last = data[-1]["timestamp"]
        return {
            "result": True,
            "data": {
                "history": data,
                "prediction": [
                    {"timestamp": last + 3600, "value": body_value},
                    {"timestamp": last + 7200, "value": body_value / 2},
                ],
            },
        }

    return _call


def test_rejects_metric_and_data_together(names):
    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        metric="disk",
        data=[{"timestamp": 1, "value": 1}],
        config=_config(),
    )
    assert result["success"] is False
    assert "只能传一个" in result["error"]


def test_pasted_points_are_ignored_when_monitor_cache_exists(names):
    record_monitor_metric_query(
        _config(execution_id="exec-cached"),
        "disk.used",
        [],
        _monitor_payload([({"instance": "host-a"}, _hourly_points(400, scale=0.01))]),
    )
    seen = {}

    def _predict(serving_id, data, steps, actor_context):
        seen["values"] = [point["value"] for point in data]
        return _ok_predict(3)(serving_id, data, steps, actor_context)

    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        metric="disk.used",
        data=[{"timestamp": 1_700_000_000_000, "value": 999999}],
        config=_config(execution_id="exec-cached"),
        predict_caller=_predict,
    )
    assert result["success"] is True
    assert 999999 not in seen["values"]
    assert result["results"][0]["instance_id"] == "instance=host-a"


def test_pasted_points_use_the_only_cached_metric(names):
    record_monitor_metric_query(
        _config(execution_id="exec-only"),
        "disk.used",
        [],
        _monitor_payload([({"instance": "host-a"}, _hourly_points(400, scale=0.01))]),
    )
    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        data=[{"timestamp": 1, "value": 999999}],
        config=_config(execution_id="exec-only"),
        predict_caller=_ok_predict(3),
    )
    assert result["success"] is True
    assert result["results"][0]["instance_id"] == "instance=host-a"


def test_pasted_points_are_rejected_when_several_metrics_are_cached(names):
    for metric in ("disk.used", "mem.used"):
        record_monitor_metric_query(
            _config(execution_id="exec-many"),
            metric,
            [],
            _monitor_payload([({"instance": "host-a"}, _hourly_points(20))]),
        )
    called = {}

    def _predict(*args, **kwargs):
        called["hit"] = True
        return _ok_predict(1)(*args, **kwargs)

    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        data=[{"timestamp": 1, "value": 999999}],
        config=_config(execution_id="exec-many"),
        predict_caller=_predict,
    )
    assert result["success"] is False
    assert "disk.used" in result["error"]
    assert "mem.used" in result["error"]
    assert "hit" not in called


def test_rejects_when_metric_and_data_are_both_missing(names):
    result = mlops_predict_timeseries_impl("summary", 7, config=_config())
    assert result["success"] is False
    assert "请传 metric" in result["error"]


def test_metric_without_monitor_result_is_rejected(names):
    result = mlops_predict_timeseries_impl("summary", 7, metric="disk.used", config=_config())
    assert result["success"] is False


def test_predict_uses_the_monitor_query_series(names):
    points = _hourly_points(400)
    record_monitor_metric_query(
        _config(execution_id="exec-pass"),
        "disk.used",
        ["10.10.50.11", "10.10.50.12"],
        _monitor_payload(
            [
                ({"instance": "10.10.50.11:9100", "device": "/dev/sda1"}, points),
                ({"instance": "10.10.50.11:9100", "device": "/dev/sdb1"}, points),
                ({"instance": "10.10.50.12:9100", "device": "/dev/sda1"}, points),
            ]
        ),
    )
    calls = []

    def _predict(serving_id, data, steps, actor_context):
        calls.append(serving_id)
        return _ok_predict(1)(serving_id, data, steps, actor_context)

    result = mlops_predict_timeseries_impl(
        "summary",
        5,
        metric="disk.used",
        instance_ids=["10.10.50.11", "10.10.50.99"],
        config=_config(execution_id="exec-pass"),
        predict_caller=_predict,
    )
    assert result["success"] is True
    assert len(calls) == 3
    assert all(not item["error"] for item in result["results"])


def test_declared_params_query_monitor_when_cache_is_missing(names, monkeypatch):
    captured = {}

    def _rpc(method, config, query_data):
        captured["method"] = method
        captured["query_data"] = query_data
        return _monitor_payload([({"instance_id": "inst-1", "instance": "10.10.50.11:9100"}, _hourly_points(400))])

    monkeypatch.setattr("apps.opspilot.metis.llm.tools.mlops.predict.call_monitor_rpc", _rpc)
    result = mlops_predict_timeseries_impl(
        "summary",
        5,
        metric="disk_used_percent",
        instance_ids=["inst-1"],
        monitor_obj_id="host",
        config=_config(execution_id="exec-declared"),
        predict_caller=_ok_predict(1),
    )
    query_data = captured["query_data"]
    assert captured["method"] == "query_monitor_data_by_metric"
    assert query_data["monitor_obj_id"] == "host"
    assert query_data["metric"] == "disk_used_percent"
    assert query_data["instance_ids"] == ["inst-1"]
    assert query_data["end"] - query_data["start"] == 14 * 24 * 60 * 60 * 1000
    assert result["success"] is True
    assert len(result["results"]) == 1


def test_boolean_result_envelope_still_reads_series(names):
    record_monitor_metric_query(
        _config(execution_id="exec-envelope"),
        "disk_used_percent",
        ["inst-1"],
        {
            "success": True,
            "data": {
                "result": True,
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {"instance_id": "inst-1", "device": "/dev/vdb1"},
                            "values": [[point["timestamp"], point["value"]] for point in _hourly_points(400)],
                        }
                    ],
                },
            },
        },
    )
    result = mlops_predict_timeseries_impl(
        "summary",
        5,
        metric="disk_used_percent",
        instance_ids=["inst-1"],
        monitor_obj_id="host",
        config=_config(execution_id="exec-envelope"),
        predict_caller=_ok_predict(1),
    )
    assert result["success"] is True
    assert result["results"][0]["error"] is None


def test_empty_monitor_result_rejects_the_batch(names):
    record_monitor_metric_query(
        _config(execution_id="exec-none"),
        "disk.used",
        ["10.10.50.11"],
        _monitor_payload([]),
    )
    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        metric="disk.used",
        config=_config(execution_id="exec-none"),
        predict_caller=_ok_predict(1),
    )
    assert result["success"] is False
    assert latest_monitor_metric_query("exec-none", "disk.used")


def test_trend_rejects_multiple_series(names):
    record_monitor_metric_query(
        _config(execution_id="exec-trend"),
        "disk.used",
        [],
        _monitor_payload(
            [
                ({"instance": "host-a"}, _hourly_points(400)),
                ({"instance": "host-b"}, _hourly_points(400)),
            ]
        ),
    )
    result = mlops_predict_timeseries_impl(
        "trend",
        7,
        metric="disk.used",
        config=_config(execution_id="exec-trend"),
    )
    assert result["success"] is False
    assert "trend" in result["error"]


def test_trend_returns_points_for_one_series(names):
    record_monitor_metric_query(
        _config(execution_id="exec-one"),
        "disk.used",
        [],
        _monitor_payload([({"instance": "host-a", "mount": "/"}, _hourly_points(400))]),
    )
    result = mlops_predict_timeseries_impl(
        "trend",
        7,
        metric="disk.used",
        config=_config(execution_id="exec-one"),
        predict_caller=_ok_predict(9),
        threshold=8,
    )
    assert result["success"] is True
    row = result["results"][0]
    assert row["instance_id"] == "instance=host-a,mount=/"
    assert row["trend"]
    assert row["over_threshold"] is True
    assert "history" not in result


def test_single_binding_ignores_model_serving_id(names):
    seen = {}

    def _predict(serving_id, data, steps, actor_context):
        seen["serving_id"] = serving_id
        return _ok_predict(3)(serving_id, data, steps, actor_context)

    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        serving_id=99,
        data=_hourly_points(400),
        config=_config(serving_ids="[7]"),
        predict_caller=_predict,
    )
    assert result["success"] is True
    assert seen["serving_id"] == 7
    assert "over_threshold" not in result["results"][0]


def test_multi_binding_rejects_unknown_serving(names):
    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        serving_id=3,
        data=_hourly_points(20),
        config=_config(serving_ids="[7, 8]"),
    )
    assert result["success"] is False
    assert "7:serving-7" in result["error"]
    assert "8:serving-8" in result["error"]


def test_series_cap(names):
    series = [({"instance": f"h{index}"}, _hourly_points(5)) for index in range(101)]
    record_monitor_metric_query(_config(execution_id="exec-cap"), "disk.used", [], _monitor_payload(series))
    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        metric="disk.used",
        config=_config(execution_id="exec-cap"),
    )
    assert result["success"] is False
    assert "100" in result["error"]


def test_one_series_failure_does_not_drop_the_other(names):
    def _predict(serving_id, data, steps, actor_context):
        if data[-1]["value"] > 100:
            return {"result": False, "message": "容器不可达"}
        return _ok_predict(4)(serving_id, data, steps, actor_context)

    record_monitor_metric_query(
        _config(execution_id="exec-mix"),
        "disk.used",
        [],
        _monitor_payload(
            [
                ({"instance": "ok"}, _hourly_points(400, scale=0.01)),
                ({"instance": "bad"}, _hourly_points(400, scale=1)),
            ]
        ),
    )
    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        metric="disk.used",
        config=_config(execution_id="exec-mix"),
        predict_caller=_predict,
    )
    assert result["success"] is True
    errors = [item for item in result["results"] if item["error"]]
    assert len(errors) == 1
    assert "容器不可达" in errors[0]["error"]


def test_all_series_failures_fail_the_batch(names, caplog):
    caplog.set_level("DEBUG", logger="opspilot")
    sentinel = 424242

    def _reject(serving_id, data, steps, actor_context):
        return {"result": False, "message": f"拒绝 {sentinel}"}

    record_monitor_metric_query(
        _config(execution_id="exec-all-fail"),
        "disk.used",
        [],
        _monitor_payload([({"instance": "only"}, _hourly_points(400))]),
    )
    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        metric="disk.used",
        config=_config(execution_id="exec-all-fail"),
        predict_caller=_reject,
    )
    assert result["success"] is False
    assert result["results"][0]["error"]
    debug_lines = [record.message for record in caplog.records if record.levelname == "DEBUG"]
    assert any("failed_stage=predict" in line and "error_type=upstream_rejected" in line for line in debug_lines)
    assert all(str(sentinel) not in line for line in debug_lines)
    info_lines = [record.message for record in caplog.records if record.levelname == "INFO"]
    assert any("event=mlops_timeseries_predict_finished" in line and "succeeded=0" in line for line in info_lines)


def test_missing_caller_identity_matches_monitor_error(names):
    config = _config()
    config["configurable"].pop("caller_identity")
    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        data=_hourly_points(400),
        config=config,
        predict_caller=_ok_predict(1),
    )
    assert result["success"] is False
    assert result["error"]


def test_metric_uses_the_latest_successful_query(names):
    execution = "exec-latest"
    record_monitor_metric_query(
        _config(execution_id=execution),
        "disk.used",
        [],
        _monitor_payload([({"instance": "old"}, _hourly_points(400, scale=0.01))]),
    )
    record_monitor_metric_query(
        _config(execution_id=execution),
        "disk.used",
        [],
        _monitor_payload([({"instance": "new"}, _hourly_points(400, scale=0.01))]),
    )
    seen = {}

    def _predict(serving_id, data, steps, actor_context):
        seen["instance_count"] = seen.get("instance_count", 0) + 1
        return _ok_predict(3)(serving_id, data, steps, actor_context)

    config = _config(execution_id=execution)
    config["configurable"].pop("timezone")
    result = mlops_predict_timeseries_impl(
        "summary",
        7,
        metric="disk.used",
        config=config,
        predict_caller=_predict,
    )
    utc = _config(execution_id=execution)
    utc["configurable"]["timezone"] = "UTC"
    utc_result = mlops_predict_timeseries_impl(
        "summary",
        7,
        metric="disk.used",
        config=utc,
        predict_caller=_predict,
    )
    assert result["success"] is True
    assert seen["instance_count"] == 2
    assert result["results"][0]["instance_id"] == "instance=new"
    assert result["results"][0]["summary"]["max_time"] != utc_result["results"][0]["summary"]["max_time"]


def test_default_concurrency_is_five():
    current = 0
    peak = 0
    lock = threading.Lock()

    def _worker(_item):
        nonlocal current, peak
        with lock:
            current += 1
            peak = max(peak, current)
        time.sleep(0.15)
        with lock:
            current -= 1
        return {"error": None}

    rows = run_bounded(list(range(8)), _worker, wall_seconds=5)
    assert len(rows) == 8
    assert peak == 5


def test_bound_serving_prompt_lists_id_and_name(names):
    prompt = get_mlops_serving_prompt({"serving_ids": "[7]"})
    assert "7:serving-7" in prompt
    text = mlops_predict_timeseries.description
    assert "哪台最危险" in text
    assert "频率乘以 steps" in text


def test_timeout_marks_unfinished(names):
    def _slow(item):
        time.sleep(1)
        return {"instance_id": item["instance_id"], "summary": {"max_value": 1}, "error": None}

    rows = run_bounded([{"instance_id": "a"}, {"instance_id": "b"}], _slow, concurrency=1, wall_seconds=0.05)
    assert any(item["error"] == "预测超时" for item in rows)


def test_builtin_tool_descriptor_exposes_serving_ids():
    class Loader:
        def get(self, key):
            return key

    data = build_builtin_mlops_tool(Loader())
    assert data["id"] == BUILTIN_MLOPS_TOOL_ID
    assert data["name"] == "mlops"
    assert any(item["key"] == "serving_ids" for item in data["params"]["kwargs"])
    assert any(item["name"] == "mlops_predict_timeseries" for item in data["tools"])


def test_language_files_define_mlops_tool():
    for name in ("zh-Hans.yaml", "en.yaml"):
        with open(f"apps/opspilot/language/{name}", encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
        assert document["tools"]["mlops"]["tools"]["mlops_predict_timeseries"]["description"]
