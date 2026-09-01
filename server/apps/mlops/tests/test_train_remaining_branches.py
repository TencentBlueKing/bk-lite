"""六套算法 TrainJob.train 剩余分支：MLflow 计数降级、抢占冲突、stop 忽略、连接失败回滚、数据集范围。"""
import types
from unittest.mock import Mock

import pandas as pd
import pydantic.root_model  # noqa
import pytest
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from apps.base.tests.factories import UserFactory
from apps.mlops.constants import DatasetReleaseStatus, TrainJobStatus
from apps.mlops.tests.test_views_actions_param import ALGO_IDS, ALGOS, _call, _model, _patch_mlflow, _view_module
from apps.mlops.utils.webhook_client import WebhookError

pytestmark = [pytest.mark.django_db, pytest.mark.integration]
factory = APIRequestFactory()


@pytest.fixture
def superuser():
    return UserFactory(username="mlops-train-su", domain="domain.com", roles=[], is_superuser=True)


def _ready_job(model_module, basename):
    TrainJob = _model(model_module, basename, "TrainJob")
    Dataset = _model(model_module, basename, "Dataset")
    Release = _model(model_module, basename, "DatasetRelease")
    ds = Dataset.objects.create(name="ds-ready", description="", team=[1])
    dv = Release.objects.create(
        name="r",
        description="",
        dataset=ds,
        version="v1",
        dataset_file="path/data.zip",
        status=DatasetReleaseStatus.PUBLISHED,
        metadata={},
        file_size=10,
    )
    tj = TrainJob.objects.create(
        name="job-ready",
        description="",
        team=[1],
        status=TrainJobStatus.PENDING,
        algorithm="demo-algo",
        dataset_version=dv,
        hyperopt_config={},
    )
    TrainJob.objects.filter(pk=tj.pk).update(config_url="path/config.json")
    tj.refresh_from_db()
    return tj


def _prep_train(monkeypatch, suffix):
    mod = _view_module(suffix)
    monkeypatch.setattr(
        mod,
        "get_mlflow_train_config",
        lambda: types.SimpleNamespace(
            bucket="b",
            minio_endpoint="e",
            mlflow_tracking_uri="u",
            minio_access_key="ak",
            minio_secret_key="sk",
        ),
    )
    monkeypatch.setattr(mod, "get_image_by_prefix", lambda p, algo: "repo/train:1")
    return mod


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_mlflow_count_and_stop_ignored(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _ready_job(model_module, basename)
    mod = _prep_train(monkeypatch, suffix)
    _patch_mlflow(
        monkeypatch,
        suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: pd.DataFrame({"run_id": ["a", "b"]}),
    )
    monkeypatch.setattr(mod.WebhookClient, "stop", staticmethod(Mock(side_effect=WebhookError("gone"))))
    train_mock = Mock(return_value={"ok": True})
    monkeypatch.setattr(mod.WebhookClient, "train", staticmethod(train_mock))
    delay = Mock()
    from apps.mlops.tasks.poll_train_job_status import poll_train_job_status as poll_task

    monkeypatch.setattr(poll_task, "delay", delay)
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"post": "train"})
    resp = _call(view, factory.post("/train/"), superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_200_OK
    train_mock.assert_called_once()
    assert delay.call_args.args[2] == 3
    tj.refresh_from_db()
    assert tj.status == TrainJobStatus.RUNNING


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_mlflow_count_exception_falls_back_to_zero(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _ready_job(model_module, basename)
    mod = _prep_train(monkeypatch, suffix)
    _patch_mlflow(
        monkeypatch,
        suffix,
        get_experiment_by_name=Mock(side_effect=RuntimeError("mlflow down")),
    )
    monkeypatch.setattr(mod.WebhookClient, "stop", staticmethod(Mock()))
    monkeypatch.setattr(mod.WebhookClient, "train", staticmethod(Mock(return_value={"ok": True})))
    delay = Mock()
    from apps.mlops.tasks.poll_train_job_status import poll_train_job_status as poll_task

    monkeypatch.setattr(poll_task, "delay", delay)
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"post": "train"})
    resp = _call(view, factory.post("/train/"), superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_200_OK
    assert delay.call_args.args[2] == 0


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_dataset_scope_error(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _ready_job(model_module, basename)
    mod = _prep_train(monkeypatch, suffix)
    vs_cls = getattr(mod, f"{basename}TrainJobViewSet")
    monkeypatch.setattr(
        vs_cls,
        "ensure_train_job_dataset_scope",
        lambda self, request, job: Response(
            {"error": "训练任务关联的数据集版本无权访问"},
            status=status.HTTP_400_BAD_REQUEST,
        ),
    )
    view = vs_cls.as_view({"post": "train"})
    resp = _call(view, factory.post("/train/"), superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "无权访问" in resp.data["error"]
    tj.refresh_from_db()
    assert tj.status == TrainJobStatus.PENDING
