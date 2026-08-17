import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.models import CollectConfig as LogCollectConfig
from apps.log.models import CollectInstance as LogCollectInstance
from apps.log.models import CollectType as LogCollectType
from apps.monitor.models import CollectConfig as MonitorCollectConfig
from apps.monitor.models import MonitorInstance, MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.node_mgmt.nats import node as node_nats
from apps.node_mgmt.utils import config_write_scope
from apps.rpc.node_mgmt import NodeMgmt

pytestmark = pytest.mark.django_db


def _log_config(config_id):
    collect_type = LogCollectType.objects.create(name=f"type-{config_id}", collector="Vector")
    instance = LogCollectInstance.objects.create(id=f"instance-{config_id}", name="日志实例", collect_type=collect_type)
    return LogCollectConfig.objects.create(
        id=config_id,
        collect_instance=instance,
        file_type="yaml",
        is_child=False,
    )


def _monitor_config(config_id):
    monitor_object = MonitorObject.objects.create(name=f"object-{config_id}", display_name="监控对象")
    monitor_instance = MonitorInstance.objects.create(
        id=f"instance-{config_id}",
        name="监控实例",
        monitor_object=monitor_object,
    )
    plugin = MonitorPlugin.objects.create(name=f"plugin-{config_id}")
    return MonitorCollectConfig.objects.create(
        id=config_id,
        monitor_instance=monitor_instance,
        monitor_plugin=plugin,
        collector="Telegraf",
        collect_type="host",
        config_type="base",
        file_type="yaml",
        is_child=False,
    )


def test_scoped_update_accepts_matching_log_mirror(monkeypatch):
    config = _log_config("log-owned")
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "update_config_content",
        lambda _self, config_id, content, env_config: calls.append((config_id, content, env_config)),
    )

    NodeMgmt(is_local_client=True).update_config_content(
        config.id,
        "content",
        {"KEY": "value"},
        source_app="log",
    )

    assert calls == [(config.id, "content", {"KEY": "value"})]


def test_scoped_update_rejects_cross_app_id_before_write(monkeypatch):
    config = _monitor_config("monitor-owned")
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "update_config_content",
        lambda *_args, **_kwargs: calls.append(True),
    )

    with pytest.raises(BaseAppException, match="配置归属校验失败"):
        NodeMgmt(is_local_client=True).update_config_content(
            config.id,
            "content",
            source_app="log",
        )

    assert calls == []


def test_legacy_update_rejects_managed_config_before_write(monkeypatch):
    config = _log_config("legacy-log-owned")
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "update_config_content",
        lambda *_args, **_kwargs: calls.append(True),
    )

    with pytest.raises(BaseAppException, match="必须使用带调用范围的接口"):
        node_nats.update_config_content({"id": config.id, "content": "content"})

    assert calls == []


def test_legacy_native_update_tolerates_uninstalled_owner_apps(monkeypatch):
    calls = []
    monkeypatch.setattr(
        config_write_scope.apps,
        "get_model",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(LookupError("app not installed")),
    )
    monkeypatch.setattr(
        node_nats.NatsService,
        "update_config_content",
        lambda _self, config_id, content, env_config: calls.append((config_id, content, env_config)),
    )

    node_nats.update_config_content({"id": "node-native", "content": "content"})

    assert calls == [("node-native", "content", None)]


def test_scoped_delete_accepts_matching_monitor_mirror(monkeypatch):
    config = _monitor_config("monitor-delete")
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "delete_configs",
        lambda _self, ids: calls.append(list(ids)),
    )

    NodeMgmt(is_local_client=True).delete_configs([config.id], source_app="monitor")

    assert calls == [[config.id]]


def test_legacy_delete_rejects_managed_config_before_write(monkeypatch):
    config = _monitor_config("legacy-monitor-owned")
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "delete_configs",
        lambda *_args, **_kwargs: calls.append(True),
    )

    with pytest.raises(BaseAppException, match="必须使用带调用范围的接口"):
        node_nats.delete_configs([config.id])

    assert calls == []


def test_scoped_delete_rejects_ambiguous_mirror_id(monkeypatch):
    _log_config("shared-config")
    _monitor_config("shared-config")
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "delete_configs",
        lambda *_args, **_kwargs: calls.append(True),
    )

    with pytest.raises(BaseAppException, match="配置归属校验失败"):
        NodeMgmt(is_local_client=True).delete_configs(["shared-config"], source_app="monitor")

    assert calls == []


def test_scoped_handler_rejects_tampered_token(monkeypatch):
    config = _log_config("tampered")
    client = NodeMgmt(is_local_client=False)
    client.client = type(
        "CaptureClient",
        (),
        {"run": lambda _self, method, token: (method, token)},
    )()
    method, token = client.update_config_content(config.id, "content", source_app="log")
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "update_config_content",
        lambda *_args, **_kwargs: calls.append(True),
    )

    with pytest.raises(BaseAppException, match="调用范围无效或已过期"):
        node_nats.update_config_content_scoped(token + "tampered")

    assert method == "update_config_content_scoped"
    assert calls == []
