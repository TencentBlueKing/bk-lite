"""补齐 MLOps 运行时清理、配置同步和算法配置校验的遗漏契约。"""

import json
from types import SimpleNamespace

import pytest
from django.http import Http404
from rest_framework import serializers
from rest_framework.response import Response

from apps.mlops.management.commands.init_algorithm_config import Command
from apps.mlops.models.mixins import ConfigSyncError
from apps.mlops.models.object_detection import ObjectDetectionTrainJob
from apps.mlops.utils.webhook_client import (
    WebhookConnectionError,
    WebhookError,
)
from apps.mlops.views import base as base_views
from apps.mlops.views.base import TeamModelViewSet


pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_train_job_complete_config_preserves_input_and_adds_runtime_sections():
    original = {"hyperparams": {"epochs": 3}, "custom": {"seed": 7}}
    job = ObjectDetectionTrainJob(
        id=42,
        algorithm="yolo11",
        max_evals=12,
        hyperopt_config=original,
    )

    config = job._build_complete_config()

    assert config == {
        "hyperparams": {"epochs": 3, "max_evals": 12},
        "custom": {"seed": 7},
        "model": {
            "type": "yolo11",
            "name": "ObjectDetection_yolo11_42",
        },
        "mlflow": {"experiment_name": "ObjectDetection_yolo11_42"},
    }
    assert original == {"hyperparams": {"epochs": 3}, "custom": {"seed": 7}}


def test_train_job_complete_config_creates_missing_hyperparams():
    job = ObjectDetectionTrainJob(
        id=7,
        algorithm="yolo11",
        max_evals=5,
        hyperopt_config={},
    )
    assert job._build_complete_config()["hyperparams"] == {"max_evals": 5}


def test_config_sync_uploads_complete_json_before_deleting_old_file(
    monkeypatch,
):
    job = ObjectDetectionTrainJob(
        id=42,
        algorithm="yolo11",
        max_evals=12,
        hyperopt_config={"hyperparams": {"epochs": 3}},
        config_url="configs/old.json",
    )
    field = job.config_url
    calls = []

    def save(field_file, filename, content, save):
        calls.append(
            (
                "save",
                filename,
                json.loads(content.read().decode("utf-8")),
                save,
            )
        )
        field_file.name = f"uploaded/{filename}"

    monkeypatch.setattr(type(field), "save", save)
    monkeypatch.setattr(
        field.storage,
        "delete",
        lambda path: calls.append(("delete", path)),
    )

    job._sync_config_to_minio()

    assert calls[0][0] == "save"
    assert calls[0][2]["hyperparams"] == {"epochs": 3, "max_evals": 12}
    assert calls[0][3] is False
    assert calls[1] == ("delete", "configs/old.json")


def test_config_sync_wraps_upload_failure_and_preserves_old_file(monkeypatch):
    job = ObjectDetectionTrainJob(
        id=42,
        algorithm="yolo11",
        max_evals=12,
        hyperopt_config={"hyperparams": {}},
        config_url="configs/old.json",
    )
    field = job.config_url
    deleted = []
    monkeypatch.setattr(
        type(field),
        "save",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("storage offline")
        ),
    )
    monkeypatch.setattr(
        field.storage, "delete", lambda path: deleted.append(path)
    )

    with pytest.raises(ConfigSyncError, match="storage offline"):
        job._sync_config_to_minio()
    assert deleted == []
    assert job.config_url.name == "configs/old.json"


def test_config_sync_tolerates_old_file_cleanup_failure(monkeypatch):
    job = ObjectDetectionTrainJob(
        id=42,
        algorithm="yolo11",
        max_evals=12,
        hyperopt_config={"hyperparams": {}},
        config_url="configs/old.json",
    )
    field = job.config_url

    def save(field_file, filename, _content, save=False):
        field_file.name = f"uploaded/{filename}"

    monkeypatch.setattr(type(field), "save", save)
    monkeypatch.setattr(
        field.storage,
        "delete",
        lambda _path: (_ for _ in ()).throw(OSError("cleanup failed")),
    )

    job._sync_config_to_minio()
    assert job.config_url.name.startswith("uploaded/config_42_")


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (None, None),
        (WebhookError("container not found"), None),
        (WebhookConnectionError("webhook offline"), 500),
        (WebhookError("permission denied"), 500),
    ],
)
def test_serving_runtime_cleanup_contract(monkeypatch, failure, expected_status):
    view = TeamModelViewSet()
    view.MLFLOW_PREFIX = "ObjectDetection"
    removed = []

    def remove(container_id):
        removed.append(container_id)
        if failure:
            raise failure

    monkeypatch.setattr(base_views.WebhookClient, "remove", remove)

    response = view.cleanup_serving_runtime(SimpleNamespace(id=9))

    assert removed == ["ObjectDetection_Serving_9"]
    if expected_status is None:
        assert response is None
    else:
        assert response.status_code == expected_status
        assert "容器清理失败" in response.data["error"]


def test_authorized_object_or_none_maps_http404():
    view = TeamModelViewSet()
    view.get_authorized_object = lambda: (_ for _ in ()).throw(Http404())
    assert view.get_authorized_object_or_none() is None


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ({"team": ["组织不匹配"], "dataset": "版本不可见"}, "组织不匹配；版本不可见"),
        ("not-a-dict", "训练任务关联的数据集版本无权访问"),
        ({}, "训练任务关联的数据集版本无权访问"),
    ],
)
def test_dataset_scope_error_is_flattened_for_api_clients(
    monkeypatch, detail, expected
):
    def reject(*_args):
        raise serializers.ValidationError(detail)

    monkeypatch.setattr(base_views, "assert_dataset_version_scope", reject)
    response = TeamModelViewSet().ensure_train_job_dataset_scope(
        SimpleNamespace(),
        SimpleNamespace(dataset_version=object(), team=[1]),
    )
    assert response.status_code == 400
    assert response.data == {"error": expected}


def test_destroy_train_job_stops_on_first_runtime_cleanup_error():
    view = TeamModelViewSet()
    blocked = Response({"error": "cleanup failed"}, status=500)
    job = SimpleNamespace(
        id=4,
        servings=SimpleNamespace(
            all=lambda: [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        ),
    )
    view.get_object = lambda: job
    calls = []

    def cleanup(serving):
        calls.append(serving.id)
        return None if serving.id == 1 else blocked

    view.cleanup_serving_runtime = cleanup
    assert view.destroy_train_job_with_runtime_cleanup(SimpleNamespace()) is blocked
    assert calls == [1, 2]


def _valid_algorithm_payload(name):
    return {
        "name": name,
        "display_name": "Demo",
        "image": "registry/demo:1",
        "scenario_description": "",
        "form_config": {"fields": []},
    }


@pytest.mark.parametrize(
    ("content", "filename", "reason"),
    [
        ("{", "broken.json", "JSON 解析失败"),
        ("[]", "list.json", "顶层必须是对象"),
        (
            json.dumps({"name": "missing"}),
            "missing.json",
            "缺少字段",
        ),
        (
            json.dumps({**_valid_algorithm_payload("extra"), "unexpected": 1}),
            "extra.json",
            "多余字段",
        ),
        (
            json.dumps({**_valid_algorithm_payload("form"), "form_config": []}),
            "form.json",
            "form_config 必须是对象",
        ),
        (
            json.dumps({**_valid_algorithm_payload("typed"), "image": 1}),
            "typed.json",
            "image 必须是字符串",
        ),
        (
            json.dumps({**_valid_algorithm_payload("blank"), "image": " "}),
            "blank.json",
            "image 不能为空字符串",
        ),
        (
            json.dumps(_valid_algorithm_payload("other")),
            "filename.json",
            "name 必须与文件名",
        ),
    ],
)
def test_algorithm_config_file_validation_reports_specific_reason(
    tmp_path, content, filename, reason
):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    valid, payload, actual_reason = Command()._load_and_validate_file(path)
    assert valid is False
    assert payload == {}
    assert reason in actual_reason


def test_algorithm_config_file_validation_accepts_exact_schema(tmp_path):
    path = tmp_path / "demo.json"
    payload = _valid_algorithm_payload("demo")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert Command()._load_and_validate_file(path) == (True, payload, "")
