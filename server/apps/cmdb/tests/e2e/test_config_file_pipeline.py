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
import jsonschema
import pytest

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


@pytest.mark.django_db
def test_nats_handler_returns_standard_envelope(monkeypatch, load_fixture):
    """nats handler 收到 payload 后返回 {result, changed, task_updated} 信封。"""
    from apps.cmdb.nats import nats as cmdb_nats

    # 拦掉真正的 process_collect_result，集中验证 handler 信封格式
    monkeypatch.setattr(
        "apps.cmdb.nats.nats.ConfigFileService.process_collect_result",
        lambda data: {"changed": True, "task_updated": True, "version_obj": None},
    )

    payload = load_fixture("config_file/02_nats_payload.json")
    result = cmdb_nats.receive_config_file_result(payload)
    assert result == {"result": True, "changed": True, "task_updated": True}


# ============================================================================
# 漂移检测：payload 字段类型错了
# ============================================================================


def test_drift_detection_invalid_status(load_schema):
    bad = {
        "collect_task_id": 1, "model_id": "host", "file_path": "/x",
        "status": "weird_status",  # ← 不在 enum
    }
    schema = load_schema("config_file/02_nats_payload.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
