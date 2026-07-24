# -*- coding: utf-8 -*-
"""apps.mlops.utils.mlflow_service 纯函数式工具的真实行为测试。

MLflow 客户端 / mlflow 模块为真实外部边界，统一打桩；其余命名构造、
指标过滤与排序、版本映射、URI 解析、错误重抛等真实逻辑全部断言。
"""
import pydantic.root_model  # noqa

from types import SimpleNamespace
import zipfile

import pytest

from apps.mlops.utils import mlflow_service as ms


# --------------------------------------------------------------------------- #
# 命名构造
# --------------------------------------------------------------------------- #
def test_build_names_join_prefix_algorithm_id():
    assert ms.build_experiment_name("TS", "ARIMA", 7) == "TS_ARIMA_7"
    assert ms.build_model_name("TS", "ARIMA", 7) == "TS_ARIMA_7"
    assert ms.build_job_id("TS", "ARIMA", 7) == "TS_ARIMA_7"


# --------------------------------------------------------------------------- #
# get_experiment_by_name
# --------------------------------------------------------------------------- #
def test_get_experiment_by_name_returns_first_match(mocker):
    exp = SimpleNamespace(experiment_id="e1")
    mocker.patch("apps.mlops.utils.mlflow_service.mlflow.set_tracking_uri")
    mocker.patch("apps.mlops.utils.mlflow_service.mlflow.search_experiments", return_value=[exp, "other"])

    assert ms.get_experiment_by_name("TS_ARIMA_7") is exp


def test_get_experiment_by_name_none_when_empty(mocker):
    mocker.patch("apps.mlops.utils.mlflow_service.mlflow.set_tracking_uri")
    mocker.patch("apps.mlops.utils.mlflow_service.mlflow.search_experiments", return_value=[])

    assert ms.get_experiment_by_name("missing") is None


def test_get_experiment_by_name_reraises_on_error(mocker):
    mocker.patch("apps.mlops.utils.mlflow_service.mlflow.set_tracking_uri")
    mocker.patch(
        "apps.mlops.utils.mlflow_service.mlflow.search_experiments",
        side_effect=RuntimeError("boom"),
    )

    with pytest.raises(RuntimeError, match="boom"):
        ms.get_experiment_by_name("x")


# --------------------------------------------------------------------------- #
# get_mlflow_client / get_experiment_runs / get_run_info 直通与错误重抛
# --------------------------------------------------------------------------- #
def test_get_mlflow_client_sets_tracking_uri(mocker):
    set_uri = mocker.patch("apps.mlops.utils.mlflow_service.mlflow.set_tracking_uri")
    fake_client = object()
    mocker.patch("apps.mlops.utils.mlflow_service.mlflow.tracking.MlflowClient", return_value=fake_client)

    assert ms.get_mlflow_client() is fake_client
    set_uri.assert_called_once()


def test_get_experiment_runs_returns_search_result(mocker):
    mocker.patch("apps.mlops.utils.mlflow_service.mlflow.set_tracking_uri")
    sentinel = object()
    search = mocker.patch("apps.mlops.utils.mlflow_service.mlflow.search_runs", return_value=sentinel)

    assert ms.get_experiment_runs("e1") is sentinel
    assert search.call_args.kwargs["experiment_ids"] == ["e1"]
    assert search.call_args.kwargs["order_by"] == ["start_time DESC"]


def test_get_experiment_runs_reraises(mocker):
    mocker.patch("apps.mlops.utils.mlflow_service.mlflow.set_tracking_uri")
    mocker.patch("apps.mlops.utils.mlflow_service.mlflow.search_runs", side_effect=RuntimeError("x"))

    with pytest.raises(RuntimeError, match="x"):
        ms.get_experiment_runs("e1")


def test_get_run_info_returns_run(mocker):
    run = SimpleNamespace(info="meta")
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=_fake_client_with_run(run))

    assert ms.get_run_info("r1") is run


def test_get_run_info_reraises(mocker):
    client = SimpleNamespace(get_run=mocker.Mock(side_effect=RuntimeError("gone")))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    with pytest.raises(RuntimeError, match="gone"):
        ms.get_run_info("r1")


def test_get_run_metrics_reraises(mocker):
    client = SimpleNamespace(get_run=mocker.Mock(side_effect=RuntimeError("err")))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    with pytest.raises(RuntimeError, match="err"):
        ms.get_run_metrics("r1")


def test_get_run_params_reraises(mocker):
    client = SimpleNamespace(get_run=mocker.Mock(side_effect=RuntimeError("err")))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    with pytest.raises(RuntimeError, match="err"):
        ms.get_run_params("r1")


def test_get_metric_history_reraises(mocker):
    client = SimpleNamespace(get_metric_history=mocker.Mock(side_effect=RuntimeError("err")))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    with pytest.raises(RuntimeError, match="err"):
        ms.get_metric_history("r1", "loss")


def test_get_model_versions_reraises(mocker):
    client = SimpleNamespace(search_model_versions=mocker.Mock(side_effect=RuntimeError("err")))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    with pytest.raises(RuntimeError, match="err"):
        ms.get_model_versions("M")


def test_resolve_model_uri_latest_reraises_non_value_error(mocker):
    client = SimpleNamespace(search_model_versions=mocker.Mock(side_effect=RuntimeError("boom")))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    with pytest.raises(RuntimeError, match="boom"):
        ms.resolve_model_uri("M", version="latest")


# --------------------------------------------------------------------------- #
# get_run_metrics: 系统指标过滤
# --------------------------------------------------------------------------- #
def _fake_client_with_run(run):
    return SimpleNamespace(get_run=lambda run_id: run)


def test_get_run_metrics_filters_system_prefixed(mocker):
    run = SimpleNamespace(data=SimpleNamespace(metrics={"loss": 1, "system/cpu": 2, "acc": 3}))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=_fake_client_with_run(run))

    result = ms.get_run_metrics("r1")

    assert set(result) == {"loss", "acc"}
    assert "system/cpu" not in result


def test_get_run_metrics_keeps_all_when_filter_disabled(mocker):
    run = SimpleNamespace(data=SimpleNamespace(metrics={"loss": 1, "system/cpu": 2}))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=_fake_client_with_run(run))

    result = ms.get_run_metrics("r1", filter_system=False)

    assert set(result) == {"loss", "system/cpu"}


# --------------------------------------------------------------------------- #
# get_metric_history: 排序与非有限值兜底
# --------------------------------------------------------------------------- #
def _metric(step, value, timestamp):
    return SimpleNamespace(step=step, value=value, timestamp=timestamp)


def test_get_metric_history_empty_returns_empty_list(mocker):
    client = SimpleNamespace(get_metric_history=lambda r, m: [])
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    assert ms.get_metric_history("r1", "loss") == []


def test_get_metric_history_sorts_by_step_when_varied(mocker):
    history = [_metric(2, 0.2, 200), _metric(0, 0.0, 100), _metric(1, 0.1, 150)]
    client = SimpleNamespace(get_metric_history=lambda r, m: history)
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    result = ms.get_metric_history("r1", "loss")

    assert [row["step"] for row in result] == [0, 1, 2]
    assert result[1] == {"step": 1, "value": 0.1, "timestamp": 150}


def test_get_metric_history_uses_index_and_timestamp_when_steps_uniform(mocker):
    # 所有 step 相同 -> 按 timestamp 排序，step 字段变为枚举索引
    history = [_metric(0, 9.0, 300), _metric(0, 7.0, 100), _metric(0, 8.0, 200)]
    client = SimpleNamespace(get_metric_history=lambda r, m: history)
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    result = ms.get_metric_history("r1", "loss")

    assert [row["step"] for row in result] == [0, 1, 2]  # 索引
    assert [row["value"] for row in result] == [7.0, 8.0, 9.0]  # 按 timestamp 升序


def test_get_metric_history_non_finite_value_becomes_zero(mocker):
    history = [_metric(0, float("inf"), 100), _metric(1, float("nan"), 200), _metric(2, 5.0, 300)]
    client = SimpleNamespace(get_metric_history=lambda r, m: history)
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    result = ms.get_metric_history("r1", "loss")

    assert [row["value"] for row in result] == [0, 0, 5.0]


# --------------------------------------------------------------------------- #
# get_run_params
# --------------------------------------------------------------------------- #
def test_get_run_params_returns_dict_copy(mocker):
    run = SimpleNamespace(data=SimpleNamespace(params={"lr": "0.01", "epochs": "10"}))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=_fake_client_with_run(run))

    assert ms.get_run_params("r1") == {"lr": "0.01", "epochs": "10"}


# --------------------------------------------------------------------------- #
# get_model_versions: 映射 + 描述兜底
# --------------------------------------------------------------------------- #
def test_get_model_versions_maps_fields_and_defaults_description(mocker):
    versions = [
        SimpleNamespace(version="2", run_id="rb", current_stage="Production", status="READY", description="ok"),
        SimpleNamespace(version="1", run_id="ra", current_stage="None", status="READY", description=None),
    ]
    client = SimpleNamespace(search_model_versions=lambda filter_string: versions)
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    result = ms.get_model_versions("MyModel")

    assert result[0] == {"version": 2, "run_id": "rb", "stage": "Production", "status": "READY", "description": "ok"}
    # description=None -> 兜底为空串；version 转 int
    assert result[1]["version"] == 1
    assert result[1]["description"] == ""


# --------------------------------------------------------------------------- #
# resolve_model_uri
# --------------------------------------------------------------------------- #
def test_resolve_model_uri_explicit_version_skips_client(mocker):
    spy = mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client")
    uri = ms.resolve_model_uri("MyModel", version="3")

    assert uri == "models:/MyModel/3"
    spy.assert_not_called()


def test_resolve_model_uri_latest_picks_newest(mocker):
    client = SimpleNamespace(search_model_versions=lambda **kw: [SimpleNamespace(version="9")])
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    assert ms.resolve_model_uri("MyModel", version="latest") == "models:/MyModel/9"


def test_resolve_model_uri_latest_raises_value_error_when_no_versions(mocker):
    client = SimpleNamespace(search_model_versions=lambda **kw: [])
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    with pytest.raises(ValueError, match="模型不存在或无可用版本"):
        ms.resolve_model_uri("MyModel", version="latest")


# --------------------------------------------------------------------------- #
# download_model_artifact: 真实 ZIP 打包逻辑（仅 download_artifacts 打桩）
# --------------------------------------------------------------------------- #
def test_download_model_artifact_zips_directory(tmp_path, mocker):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.pkl").write_bytes(b"weights")
    (model_dir / "MLmodel").write_text("flavor: sklearn")

    client = SimpleNamespace(download_artifacts=lambda run_id, artifact_path, dst_path: str(model_dir))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    archive = ms.download_model_artifact("r1", "model")
    try:
        assert archive.fileno() >= 0
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
        # 相对父目录归档，含目录前缀
        assert "model/model.pkl" in names
        assert "model/MLmodel" in names
    finally:
        archive.close()


def test_download_model_artifact_zips_single_file(tmp_path, mocker):
    single = tmp_path / "model.pkl"
    single.write_bytes(b"weights")

    client = SimpleNamespace(download_artifacts=lambda run_id, artifact_path, dst_path: str(single))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    archive = ms.download_model_artifact("r1", "model.pkl")
    try:
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
        # 单文件场景：仅以文件名归档
        assert names == ["model.pkl"]
    finally:
        archive.close()


def test_download_model_artifact_missing_path_raises(mocker):
    client = SimpleNamespace(download_artifacts=lambda run_id, artifact_path, dst_path: "/nonexistent/path/xyz")
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    with pytest.raises(FileNotFoundError, match="模型文件不存在"):
        ms.download_model_artifact("r1")


# --------------------------------------------------------------------------- #
# delete_experiment_and_model: 幂等跳过 / 删除 / 异常重抛
# --------------------------------------------------------------------------- #
class _DeleteClient:
    def __init__(self, get_model_exc=None):
        self.deleted_models = []
        self.deleted_experiments = []
        self._get_model_exc = get_model_exc

    def get_registered_model(self, name):
        if self._get_model_exc:
            raise self._get_model_exc
        return SimpleNamespace(name=name)

    def delete_registered_model(self, name):
        self.deleted_models.append(name)

    def delete_experiment(self, exp_id):
        self.deleted_experiments.append(exp_id)


def test_delete_experiment_and_model_deletes_both(mocker):
    client = _DeleteClient()
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)
    mocker.patch(
        "apps.mlops.utils.mlflow_service.get_experiment_by_name",
        return_value=SimpleNamespace(experiment_id="e9"),
    )

    ms.delete_experiment_and_model("TS_ARIMA_1", "TS_ARIMA_1")

    assert client.deleted_models == ["TS_ARIMA_1"]
    assert client.deleted_experiments == ["e9"]


def test_delete_experiment_and_model_skips_missing_model(mocker):
    client = _DeleteClient(get_model_exc=Exception("RESOURCE_DOES_NOT_EXIST"))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)
    mocker.patch("apps.mlops.utils.mlflow_service.get_experiment_by_name", return_value=None)

    ms.delete_experiment_and_model("exp", "model")

    # 模型不存在被跳过，未删除模型，也无实验
    assert client.deleted_models == []
    assert client.deleted_experiments == []


def test_delete_experiment_and_model_reraises_unexpected_model_error(mocker):
    client = _DeleteClient(get_model_exc=Exception("PERMISSION_DENIED"))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)
    mocker.patch("apps.mlops.utils.mlflow_service.get_experiment_by_name", return_value=None)

    with pytest.raises(Exception, match="PERMISSION_DENIED"):
        ms.delete_experiment_and_model("exp", "model")


# --------------------------------------------------------------------------- #
# delete_run
# --------------------------------------------------------------------------- #
def test_delete_run_calls_client(mocker):
    deleted = []
    client = SimpleNamespace(delete_run=lambda r: deleted.append(r))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    ms.delete_run("run-123")

    assert deleted == ["run-123"]


def test_delete_run_reraises_on_error(mocker):
    client = SimpleNamespace(delete_run=mocker.Mock(side_effect=RuntimeError("nope")))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    with pytest.raises(RuntimeError, match="nope"):
        ms.delete_run("r")
