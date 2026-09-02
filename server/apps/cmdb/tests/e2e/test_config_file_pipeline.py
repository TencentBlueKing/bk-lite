"""配置文件采集端到端流水线测试 —— 走 NATS 订阅那条独特路径。

链路：
  Stargazer 采集脚本读取配置文件 → 序列化 NATS payload
    → nats publish "receive_config_file_result"
    → CMDB nats.py @nats_client.register receive_config_file_result handler
    → ConfigFileService.process_collect_result
    → ConfigFileVersion DB 记录 + collect task 状态更新

跟其他采集对象的差异：
  - 不走 VictoriaMetrics（配置文件内容不是时序指标）
  - 通过 NATS 直接推送 → CMDB 收到回调
  - 内容 base64 编码后落 MinIO（本测试用 process_collect_result 的早返分支）
"""
import base64
import hashlib

import jsonschema
import pytest
import tomllib

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.config_file_version import ConfigFileContentStatus, ConfigFileVersion, ConfigFileVersionStatus
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.services.config_file_content_lifecycle import ConfigFileContentLifecycle
from apps.cmdb.services.config_file_service import ConfigFileService
from apps.core.exceptions.base_app_exception import BaseAppException

# ============================================================================
# 段 2: NATS payload 契约校验
# ============================================================================


def test_nats_payload_matches_schema(load_fixture, load_schema):
    payload = load_fixture("config_file/02_nats_payload.json")
    schema = load_schema("config_file/02_nats_payload.schema.json")
    jsonschema.validate(payload, schema)


# ============================================================================
# 段 3+4: CMDB 端接收 NATS → ConfigFileService 处理
# ============================================================================


@pytest.mark.django_db
def test_payload_passes_normalize(load_fixture):
    """payload → _normalize_collect_payload 不抛、产出合法 dict。"""
    payload = load_fixture("config_file/02_nats_payload.json")
    normalized = ConfigFileService._normalize_collect_payload(payload)
    assert normalized["collect_task_id"] == 8001
    assert normalized["file_path"] == "/etc/nginx/nginx.conf"


@pytest.mark.django_db
def test_missing_task_id_raises():
    """缺 collect_task_id / task_id 必须抛 BaseAppException。"""
    bad = {"status": "success", "model_id": "host"}
    with pytest.raises(BaseAppException):
        ConfigFileService.process_collect_result(bad)


@pytest.mark.django_db
def test_unknown_task_id_raises():
    """任务不存在必须抛 BaseAppException。"""
    bad = {"collect_task_id": 999999999, "status": "success", "model_id": "host"}
    with pytest.raises(BaseAppException):
        ConfigFileService.process_collect_result(bad)


# ============================================================================
# CMDB 端 NATS handler 入口（@nats_client.register receive_config_file_result）
# ============================================================================


def test_nats_handler_returns_standard_envelope(monkeypatch, load_fixture):
    """nats handler 收到 payload 后返回传输 ack + 业务处理状态信封。"""
    from apps.cmdb.nats import nats as cmdb_nats

    # 拦掉真正的 process_collect_result，集中验证 handler 信封格式
    monkeypatch.setattr(
        "apps.cmdb.nats.nats.ConfigFileService.process_collect_result",
        lambda data: {"changed": True, "task_updated": True, "version_obj": None},
    )

    payload = load_fixture("config_file/02_nats_payload.json")
    result = cmdb_nats.receive_config_file_result(payload)
    assert result == {
        "result": True,
        "processed": True,
        "error": "",
        "changed": True,
        "task_updated": True,
    }


def test_nats_handler_marks_business_failure_when_service_returns_error(monkeypatch, load_fixture):
    """服务层已错误闭环时，handler 仍 ack 传输但不能表示业务成功。"""
    from apps.cmdb.nats import nats as cmdb_nats

    monkeypatch.setattr(
        "apps.cmdb.nats.nats.ConfigFileService.process_collect_result",
        lambda data: {
            "version_obj": None,
            "changed": False,
            "task_updated": True,
            "error": "配置文件采集回调缺少目标实例标识",
        },
    )

    payload = load_fixture("config_file/02_nats_payload.json")
    result = cmdb_nats.receive_config_file_result(payload)

    assert result == {
        "result": True,
        "processed": False,
        "error": "配置文件采集回调缺少目标实例标识",
        "changed": False,
        "task_updated": True,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("model_id", "driver_type", "params", "instance", "credential", "expected_plugin", "expected_file_path"),
    [
        (
            "config_file",
            "job",
            {"config_file_path": "/etc/nginx/nginx.conf"},
            {
                "_id": "101",
                "inst_uuid": "123e4567-e89b-42d3-a456-426614174000",
                "model_id": "host",
                "inst_name": "10.0.0.8",
                "ip_addr": "10.0.0.8",
            },
            {"username": "readonly", "password": "test-secret", "port": 22},
            "config_file_info",
            "/etc/nginx/nginx.conf",
        ),
        (
            "network_config_file",
            "protocol",
            {"config_name": "running-config", "commands": "show running-config"},
            {
                "_id": "102",
                "inst_uuid": "223e4567-e89b-42d3-a456-426614174000",
                "model_id": "switch",
                "inst_name": "switch-01",
                "ip_addr": "10.0.0.9",
                "brand": "Cisco",
            },
            {"username": "readonly", "password": "test-secret", "port": 22},
            "network_config_file_info",
            "network://running-config",
        ),
    ],
    ids=["host", "network"],
)
def test_cmdb_child_config_to_nats_handler_to_version_storage_chain(
    monkeypatch,
    django_capture_on_commit_callbacks,
    model_id,
    driver_type,
    params,
    instance,
    credential,
    expected_plugin,
    expected_file_path,
):
    from apps.cmdb.nats import nats as cmdb_nats

    task = CollectModels.objects.create(
        name=f"{model_id}-chain",
        task_type="config_file",
        model_id=model_id,
        driver_type=driver_type,
        is_interval=True,
        cycle_value_type="cycle",
        cycle_value="5",
        instances=[instance],
        params=params,
        access_point=[{"id": 9}],
        credential=[credential],
        timeout=60,
    )

    child_configs = NodeParamsFactory.get_node_params(task).main()

    assert len(child_configs) == 1
    rendered = tomllib.loads(child_configs[0]["content"])
    telegraf_input = rendered["inputs"]["prometheus"][0]
    headers = telegraf_input["http_headers"]
    assert telegraf_input["namedrop"] == ["collection_request_accepted"]
    assert headers["cmdbplugin_name"] == expected_plugin
    assert headers["cmdbcallback_subject"] == "receive_config_file_result"
    assert headers["cmdbprotocol_version"] == "2"
    assert "cmdbexecution_id" not in headers

    content = f"collected configuration for {instance['inst_uuid']}"
    callback_payload = {
        "collect_task_id": int(headers["cmdbcollect_task_id"]),
        "protocol_version": headers["cmdbprotocol_version"],
        "instance_uuid": headers["cmdbtarget_instance_uuid"],
        "instance_name": instance["inst_name"],
        "model_id": headers["cmdbtarget_model_id"],
        "file_path": expected_file_path,
        "file_name": expected_file_path.rsplit("/", 1)[-1],
        "version": "1700000000000",
        "status": "success",
        "size": len(content.encode()),
        "error": "",
        "content_base64": base64.b64encode(content.encode()).decode(),
    }
    monkeypatch.setattr(
        ConfigFileContentLifecycle,
        "stage_content",
        staticmethod(lambda _content: "tmp/config-file/chain.txt"),
    )
    monkeypatch.setattr(
        ConfigFileContentLifecycle,
        "publish_version",
        staticmethod(
            lambda version_id: bool(
                ConfigFileVersion.objects.filter(id=version_id).update(
                    content_status=ConfigFileContentStatus.READY,
                    temp_content_key="",
                )
            )
        ),
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = cmdb_nats.receive_config_file_result(callback_payload)

    assert response == {
        "result": True,
        "processed": True,
        "error": "",
        "changed": True,
        "task_updated": True,
    }
    latest = ConfigFileService.get_latest_version(
        task.id,
        instance["inst_uuid"],
        expected_file_path,
    )
    assert latest is not None
    assert latest.status == ConfigFileVersionStatus.SUCCESS
    assert latest.content_status == ConfigFileContentStatus.READY
    assert latest.content_hash == hashlib.sha256(content.encode()).hexdigest()
    task.refresh_from_db()
    assert task.collect_data["config_file"]["status"] == "success"
    assert task.collect_data["config_file"]["success_count"] == 1


# ============================================================================
# 漂移检测：payload 字段类型错了
# ============================================================================


def test_drift_detection_invalid_status(load_schema):
    bad = {
        "collect_task_id": 1,
        "protocol_version": "2",
        "instance_uuid": "123e4567-e89b-42d3-a456-426614174000",
        "model_id": "host",
        "file_path": "/x",
        "status": "weird_status",  # ← 不在 enum
    }
    schema = load_schema("config_file/02_nats_payload.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# ============================================================================
# Task 2.6: config_file 真实化覆盖(NATS 路径)
# ============================================================================


def test_config_file_a_b_alignment(load_fixture, load_schema):
    """config_file A/B 端对齐走 NATS 路径占位校验。

    真实采集路径是 Stargazer 通过 NATS publish 'receive_config_file_result',
    不走 VM pipeline,因此 A 端 metric / B 端 pipeline.run_full_pipeline_generic
    均不适用。本测试只验证:
      - 01 fixture 存在(placeholder)
      - 04 schema 反映 ConfigFileVersion 实例结构
      - 02 NATS payload schema 仍合规
    """
    from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def

    raw = load_fixture("config_file/01_stargazer_raw.json")
    assert raw["_placeholder_reason"] is not None

    nats_payload = load_fixture("config_file/02_nats_payload.json")
    nats_schema = load_schema("config_file/02_nats_payload.schema.json")
    jsonschema.validate(nats_payload, nats_schema)

    # 04 schema 反映 ConfigFileVersion 实例结构
    model_fields = get_model_field_def("config_file")
    assert "file_path" in model_fields
    assert "status" in model_fields
    assert "file_size" in model_fields
    assert model_fields["file_size"].field_type == "int"
    # status 字段是 choice 枚举
    assert model_fields["status"].choice is not None
    assert "success" in model_fields["status"].choice
