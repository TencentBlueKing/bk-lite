"""Parametrized serializer-validation tests across the six MLOps algorithms.

Targets the shared validation surface that every algorithm's serializers
expose: ``validate_team`` (team scoping), ``validate_dataset`` /
``validate_train_job`` (parent ownership), TrainJob.validate (dataset-version
scope) and Serving.validate (parent-team match).
"""
import importlib
import io
from types import SimpleNamespace

import pydantic.root_model  # noqa
import pytest
from rest_framework import serializers as drf_serializers

from .conftest import make_serializer_context

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# (suffix, model_module, basename)
ALGOS = [
    ("anomaly_detection", "anomaly_detection", "AnomalyDetection"),
    ("classification", "classification", "Classification"),
    ("log_clustering", "log_clustering", "LogClustering"),
    ("timeseries_predict", "timeseries_predict", "TimeSeriesPredict"),
    ("image_classification", "image_classification", "ImageClassification"),
    ("object_detection", "object_detection", "ObjectDetection"),
]
ALGO_IDS = [a[0] for a in ALGOS]

# TrainJob serializers that REQUIRE a dataset_version on create.
DATASET_VERSION_REQUIRED = {"anomaly_detection", "log_clustering", "timeseries_predict"}


def _ser_module(suffix):
    return importlib.import_module(f"apps.mlops.serializers.{suffix}")


def _model_module(model_module):
    return importlib.import_module(f"apps.mlops.models.{model_module}")


def _model(model_module, basename, kind):
    return getattr(_model_module(model_module), f"{basename}{kind}")


def _serializer(ser_module, basename, kind):
    return getattr(ser_module, f"{basename}{kind}Serializer")


# ---------------- Dataset.validate_team ----------------


@pytest.mark.parametrize("suffix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_dataset_validate_team_passes_allowed(monkeypatch, mlops_user, suffix, model_module, basename):
    context = make_serializer_context(monkeypatch, mlops_user)
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "Dataset")(context=context)
    # mlops_user belongs to teams [1]; validate_requested_teams should accept [1]
    assert serializer.validate_team([1]) == [1]


@pytest.mark.parametrize("suffix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_dataset_validate_team_rejects_empty(monkeypatch, mlops_user, suffix, model_module, basename):
    context = make_serializer_context(monkeypatch, mlops_user)
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "Dataset")(context=context)
    with pytest.raises(drf_serializers.ValidationError):
        serializer.validate_team([])


@pytest.mark.parametrize("suffix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_dataset_validate_team_rejects_non_int(monkeypatch, mlops_user, suffix, model_module, basename):
    context = make_serializer_context(monkeypatch, mlops_user)
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "Dataset")(context=context)
    with pytest.raises(drf_serializers.ValidationError):
        serializer.validate_team(["abc"])


# ---------------- TrainJob.validate (dataset_version scope) ----------------


@pytest.mark.parametrize("suffix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_job_validate_allows_matching_scope(monkeypatch, mlops_user, suffix, model_module, basename):
    context = make_serializer_context(monkeypatch, mlops_user)
    Dataset = _model(model_module, basename, "Dataset")
    Release = _model(model_module, basename, "DatasetRelease")
    ds = Dataset.objects.create(name="ds", description="", team=[1])
    from apps.mlops.constants import DatasetReleaseStatus

    dv = Release.objects.create(
        name="r", description="", dataset=ds, version="v1",
        dataset_file="path/file.zip", status=DatasetReleaseStatus.PUBLISHED,
        metadata={}, file_size=10,
    )
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "TrainJob")(context=context)
    attrs = serializer.validate({"dataset_version": dv, "team": [1]})
    assert attrs["dataset_version"] == dv


@pytest.mark.parametrize("suffix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_job_validate_rejects_team_mismatch(monkeypatch, mlops_user, suffix, model_module, basename):
    context = make_serializer_context(monkeypatch, mlops_user)
    Dataset = _model(model_module, basename, "Dataset")
    Release = _model(model_module, basename, "DatasetRelease")
    # dataset owned by team [1], train_job claims team [2] -> parent mismatch
    ds = Dataset.objects.create(name="ds", description="", team=[1])
    from apps.mlops.constants import DatasetReleaseStatus

    dv = Release.objects.create(
        name="r", description="", dataset=ds, version="v1",
        dataset_file="path/file.zip", status=DatasetReleaseStatus.PUBLISHED,
        metadata={}, file_size=10,
    )
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "TrainJob")(context=context)
    with pytest.raises(drf_serializers.ValidationError):
        serializer.validate({"dataset_version": dv, "team": [2]})


@pytest.mark.parametrize("suffix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_job_validate_none_dataset_version(monkeypatch, mlops_user, suffix, model_module, basename):
    context = make_serializer_context(monkeypatch, mlops_user)
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "TrainJob")(context=context)
    if suffix in DATASET_VERSION_REQUIRED:
        # create path requires a dataset_version -> rejects None
        with pytest.raises(drf_serializers.ValidationError):
            serializer.validate({"dataset_version": None, "team": [1]})
    else:
        attrs = serializer.validate({"dataset_version": None, "team": [1]})
        assert attrs["dataset_version"] is None


# ---------------- Serving.validate_train_job + validate ----------------


@pytest.mark.parametrize("suffix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_validate_train_job_ownership(monkeypatch, mlops_user, suffix, model_module, basename):
    context = make_serializer_context(monkeypatch, mlops_user)
    TrainJob = _model(model_module, basename, "TrainJob")
    from apps.mlops.constants import TrainJobStatus

    tj = TrainJob.objects.create(
        name="job", description="", team=[1], status=TrainJobStatus.COMPLETED,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "Serving")(context=context)
    assert serializer.validate_train_job(tj) == tj


@pytest.mark.parametrize("suffix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_validate_parent_team_match(monkeypatch, mlops_user, suffix, model_module, basename):
    context = make_serializer_context(monkeypatch, mlops_user)
    TrainJob = _model(model_module, basename, "TrainJob")
    from apps.mlops.constants import TrainJobStatus

    tj = TrainJob.objects.create(
        name="job", description="", team=[1], status=TrainJobStatus.COMPLETED,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "Serving")(context=context)
    # matching team -> ok
    attrs = serializer.validate({"train_job": tj, "team": [1]})
    assert attrs["train_job"] == tj


@pytest.mark.parametrize("suffix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_validate_parent_team_mismatch(monkeypatch, mlops_user, suffix, model_module, basename):
    context = make_serializer_context(monkeypatch, mlops_user)
    TrainJob = _model(model_module, basename, "TrainJob")
    from apps.mlops.constants import TrainJobStatus

    tj = TrainJob.objects.create(
        name="job", description="", team=[1], status=TrainJobStatus.COMPLETED,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "Serving")(context=context)
    with pytest.raises(drf_serializers.ValidationError):
        serializer.validate({"train_job": tj, "team": [2]})


# ---------------- TrainData.validate_train_data (CSV) ----------------

# (suffix, model_module, basename, required_columns, numeric_null_col)
CSV_ALGOS = [
    ("anomaly_detection", "anomaly_detection", "AnomalyDetection",
     ["timestamp", "value", "label"], "value"),
    ("classification", "classification", "Classification",
     ["text", "label"], None),
    ("timeseries_predict", "timeseries_predict", "TimeSeriesPredict",
     ["timestamp", "value"], "value"),
]
CSV_IDS = [a[0] for a in CSV_ALGOS]


def _train_request():
    return SimpleNamespace(
        query_params={},
        COOKIES={"current_team": "1"},
        user=SimpleNamespace(is_superuser=False, group_list=[{"id": 1}]),
    )


def _csv_serializer(monkeypatch, mlops_user, suffix, basename):
    context = make_serializer_context(monkeypatch, mlops_user)
    context["request"] = _train_request()
    sm = _ser_module(suffix)
    return _serializer(sm, basename, "TrainData")(context=context)


@pytest.mark.parametrize("suffix,model_module,basename,cols,null_col", CSV_ALGOS, ids=CSV_IDS)
def test_validate_train_data_valid(monkeypatch, mlops_user, suffix, model_module, basename, cols, null_col):
    header = ",".join(cols)
    # build two valid rows
    row = ",".join(["x" if c in ("text",) else ("2020-01-01 00:00:00" if c == "timestamp" else "1.0") for c in cols])
    csv = io.BytesIO(f"{header}\n{row}\n{row}\n".encode())
    s = _csv_serializer(monkeypatch, mlops_user, suffix, basename)
    result = s.validate_train_data(csv)
    assert result is csv
    assert csv.tell() == 0  # pointer reset


@pytest.mark.parametrize("suffix,model_module,basename,cols,null_col", CSV_ALGOS, ids=CSV_IDS)
def test_validate_train_data_missing_column(monkeypatch, mlops_user, suffix, model_module, basename, cols, null_col):
    # drop the last required column
    partial_cols = cols[:-1]
    header = ",".join(partial_cols) if partial_cols else "irrelevant"
    row = ",".join(["x"] * max(1, len(partial_cols)))
    csv = io.BytesIO(f"{header}\n{row}\n".encode())
    s = _csv_serializer(monkeypatch, mlops_user, suffix, basename)
    with pytest.raises(drf_serializers.ValidationError) as exc:
        s.validate_train_data(csv)
    assert "缺少必需列" in str(exc.value)
    assert cols[-1] in str(exc.value)


@pytest.mark.parametrize("suffix,model_module,basename,cols,null_col", CSV_ALGOS, ids=CSV_IDS)
def test_validate_train_data_null_numeric(monkeypatch, mlops_user, suffix, model_module, basename, cols, null_col):
    if null_col is None:
        pytest.skip(f"{suffix} has no numeric null-check column")
    # build a row with an empty value in the numeric column
    cells = []
    for c in cols:
        if c == null_col:
            cells.append("")  # null
        elif c == "timestamp":
            cells.append("2020-01-01 00:00:00")
        elif c == "text":
            cells.append("x")
        else:
            cells.append("1")
    good_cells = ["2020-01-02 00:00:00" if c == "timestamp" else ("x" if c == "text" else "2") for c in cols]
    header = ",".join(cols)
    csv = io.BytesIO(f"{header}\n{','.join(cells)}\n{','.join(good_cells)}\n".encode())
    s = _csv_serializer(monkeypatch, mlops_user, suffix, basename)
    with pytest.raises(drf_serializers.ValidationError) as exc:
        s.validate_train_data(csv)
    assert null_col in str(exc.value)


# ---------------- DatasetRelease._create_from_files ----------------

from unittest.mock import Mock  # noqa: E402

# (suffix, model_module, basename, task_module)
RELEASE_ALGOS = [
    ("anomaly_detection", "anomaly_detection", "AnomalyDetection", "anomaly_detection"),
    ("classification", "classification", "Classification", "classification"),
    ("log_clustering", "log_clustering", "LogClustering", "log_clustering"),
    ("timeseries_predict", "timeseries_predict", "TimeSeriesPredict", "timeseries"),
    ("image_classification", "image_classification", "ImageClassification", "image_classification"),
    ("object_detection", "object_detection", "ObjectDetection", "object_detection"),
]
RELEASE_IDS = [a[0] for a in RELEASE_ALGOS]


@pytest.mark.parametrize("suffix,model_module,basename,task_module", RELEASE_ALGOS, ids=RELEASE_IDS)
def test_create_from_files_missing_train_data_raises(monkeypatch, mlops_user, suffix, model_module, basename, task_module):
    context = make_serializer_context(monkeypatch, mlops_user)
    Dataset = _model(model_module, basename, "Dataset")
    dataset = Dataset.objects.create(name="ds", description="", team=[1])
    monkeypatch.setattr(
        f"apps.mlops.tasks.{task_module}.publish_dataset_release_async.delay", Mock()
    )
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "DatasetRelease")(context=context)
    with pytest.raises(drf_serializers.ValidationError) as exc:
        serializer._create_from_files({"dataset": dataset, "version": "v9"}, 9991, 9992, 9993)
    assert "训练数据文件不存在" in str(exc.value)


@pytest.mark.parametrize("suffix,model_module,basename,task_module", RELEASE_ALGOS, ids=RELEASE_IDS)
def test_create_from_files_success_creates_pending(monkeypatch, mlops_user, suffix, model_module, basename, task_module):
    context = make_serializer_context(monkeypatch, mlops_user)
    Dataset = _model(model_module, basename, "Dataset")
    TrainData = _model(model_module, basename, "TrainData")
    dataset = Dataset.objects.create(name="ds", description="", team=[1])
    train = TrainData.objects.create(name="t", dataset=dataset, is_train_data=True)
    val = TrainData.objects.create(name="v", dataset=dataset, is_val_data=True)
    test = TrainData.objects.create(name="te", dataset=dataset, is_test_data=True)
    delay_mock = Mock(return_value=SimpleNamespace(id="task-1"))
    monkeypatch.setattr(
        f"apps.mlops.tasks.{task_module}.publish_dataset_release_async.delay", delay_mock
    )
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "DatasetRelease")(context=context)
    release = serializer._create_from_files(
        {"dataset": dataset, "version": "v3"}, train.id, val.id, test.id
    )
    assert release.status == "pending"
    assert release.file_size == 0
    delay_mock.assert_called_once_with(release.id, train.id, val.id, test.id)


@pytest.mark.parametrize("suffix,model_module,basename,task_module", RELEASE_ALGOS, ids=RELEASE_IDS)
def test_create_from_files_dispatch_failure_marks_failed(monkeypatch, mlops_user, suffix, model_module, basename, task_module):
    context = make_serializer_context(monkeypatch, mlops_user)
    Dataset = _model(model_module, basename, "Dataset")
    TrainData = _model(model_module, basename, "TrainData")
    dataset = Dataset.objects.create(name="ds", description="", team=[1])
    train = TrainData.objects.create(name="t", dataset=dataset, is_train_data=True)
    val = TrainData.objects.create(name="v", dataset=dataset, is_val_data=True)
    test = TrainData.objects.create(name="te", dataset=dataset, is_test_data=True)

    def boom(*a, **k):
        raise RuntimeError("broker down")

    monkeypatch.setattr(
        f"apps.mlops.tasks.{task_module}.publish_dataset_release_async.delay", boom
    )
    sm = _ser_module(suffix)
    serializer = _serializer(sm, basename, "DatasetRelease")(context=context)
    with pytest.raises(drf_serializers.ValidationError) as exc:
        serializer._create_from_files(
            {"dataset": dataset, "version": "v4"}, train.id, val.id, test.id
        )
    assert "投递异步任务失败" in str(exc.value)
    # the created release was marked failed
    Release = _model(model_module, basename, "DatasetRelease")
    rel = Release.objects.get(dataset=dataset, version="v4")
    assert rel.status == "failed"
