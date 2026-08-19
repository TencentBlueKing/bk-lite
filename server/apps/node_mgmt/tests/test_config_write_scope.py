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


@pytest.fixture(autouse=True)
def _enable_config_write_scope(monkeypatch):
    monkeypatch.setenv("NODE_CONFIG_WRITE_SCOPE_SIGNING_ENABLED", "true")
    monkeypatch.setenv("NODE_CONFIG_WRITE_SCOPE_ENFORCEMENT_ENABLED", "true")


def _log_config(config_id, *, is_child=False):
    collect_type = LogCollectType.objects.create(name=f"type-{config_id}", collector="Vector")
    instance = LogCollectInstance.objects.create(id=f"instance-{config_id}", name="日志实例", collect_type=collect_type)
    return LogCollectConfig.objects.create(
        id=config_id,
        collect_instance=instance,
        file_type="yaml",
        is_child=is_child,
    )


def _monitor_config(config_id, *, is_child=False):
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
        is_child=is_child,
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


def test_base_scoped_update_rejects_child_mirror_with_same_id(monkeypatch):
    config = _log_config("log-child-only", is_child=True)
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


def test_scoped_child_update_accepts_matching_log_mirror(monkeypatch):
    config = _log_config("log-child", is_child=True)
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "update_child_config_content",
        lambda _self, config_id, content, env_config: calls.append((config_id, content, env_config)),
    )

    NodeMgmt(is_local_client=True).update_child_config_content(
        config.id,
        "content",
        {"KEY": "value"},
        source_app="log",
    )

    assert calls == [(config.id, "content", {"KEY": "value"})]


def test_scoped_child_update_rejects_cross_app_id_before_write(monkeypatch):
    config = _monitor_config("monitor-child", is_child=True)
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "update_child_config_content",
        lambda *_args, **_kwargs: calls.append(True),
    )

    with pytest.raises(BaseAppException, match="配置归属校验失败"):
        NodeMgmt(is_local_client=True).update_child_config_content(
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


def test_legacy_managed_update_shadow_mode_allows_and_observes(monkeypatch):
    config = _log_config("shadow-log-owned")
    calls = []
    warnings = []
    monkeypatch.setenv("NODE_CONFIG_WRITE_SCOPE_ENFORCEMENT_ENABLED", "false")
    monkeypatch.setattr(node_nats.logger, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(
        node_nats.NatsService,
        "update_config_content",
        lambda _self, config_id, content, env_config: calls.append((config_id, content, env_config)),
    )

    node_nats.update_config_content({"id": config.id, "content": "content"})

    assert calls == [(config.id, "content", None)]
    assert warnings == [("legacy managed config write observed; is_child=%s config_count=%s", False, 1)]


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


def test_scoped_update_tolerates_uninstalled_source_owner_model(monkeypatch):
    original_get_model = config_write_scope.apps.get_model
    calls = []

    def get_model(app_label, model_name):
        if app_label == "log":
            raise LookupError("app not installed")
        return original_get_model(app_label, model_name)

    monkeypatch.setattr(config_write_scope.apps, "get_model", get_model)
    monkeypatch.setattr(
        node_nats.NatsService,
        "update_config_content",
        lambda _self, config_id, content, env_config: calls.append((config_id, content, env_config)),
    )

    NodeMgmt(is_local_client=True).update_config_content("modular-log", "content", source_app="log")

    assert calls == [("modular-log", "content", None)]


def test_scoped_update_rejects_installed_other_owner_when_source_model_is_uninstalled(monkeypatch):
    config = _monitor_config("known-monitor-owner")
    original_get_model = config_write_scope.apps.get_model

    def get_model(app_label, model_name):
        if app_label == "log":
            raise LookupError("app not installed")
        return original_get_model(app_label, model_name)

    monkeypatch.setattr(config_write_scope.apps, "get_model", get_model)

    with pytest.raises(BaseAppException, match="配置归属校验失败"):
        NodeMgmt(is_local_client=True).update_config_content(config.id, "content", source_app="log")


def test_legacy_native_delete_is_preserved_when_owner_apps_are_installed(monkeypatch):
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "delete_configs",
        lambda _self, ids: calls.append(list(ids)),
    )

    node_nats.delete_configs(["node-native"])

    assert calls == [["node-native"]]


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


def test_legacy_child_delete_rejects_managed_config_before_write(monkeypatch):
    config = _monitor_config("legacy-monitor-child", is_child=True)
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "delete_child_configs",
        lambda *_args, **_kwargs: calls.append(True),
    )

    with pytest.raises(BaseAppException, match="必须使用带调用范围的接口"):
        node_nats.delete_child_configs([config.id])

    assert calls == []


def test_scoped_child_delete_accepts_matching_monitor_mirror(monkeypatch):
    config = _monitor_config("monitor-child-delete", is_child=True)
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "delete_child_configs",
        lambda _self, ids: calls.append(list(ids)),
    )

    NodeMgmt(is_local_client=True).delete_child_configs([config.id], source_app="monitor")

    assert calls == [[config.id]]


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


def test_scoped_handler_rejects_expired_token(monkeypatch):
    now = [1_700_000_000]
    monkeypatch.setattr(config_write_scope.signing.time, "time", lambda: now[0])
    token = config_write_scope.build_config_write_scope(
        "log",
        "update",
        {"id": "expired", "content": "content", "env_config": None},
    )
    now[0] += config_write_scope.CONFIG_WRITE_SCOPE_MAX_AGE_SECONDS + 1

    with pytest.raises(BaseAppException, match="调用范围无效或已过期"):
        node_nats.update_config_content_scoped(token)


def test_update_token_cannot_be_reused_for_child_update(monkeypatch):
    token = config_write_scope.build_config_write_scope(
        "log",
        "update",
        {"id": "base", "content": "content", "env_config": None},
    )
    calls = []
    monkeypatch.setattr(
        node_nats.NatsService,
        "update_child_config_content",
        lambda *_args, **_kwargs: calls.append(True),
    )

    with pytest.raises(BaseAppException, match="调用范围无效或已过期"):
        node_nats.update_child_config_content_scoped(token)

    assert calls == []


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [("invalid", 60), ("600", 300), ("0", 1)],
)
def test_scope_ttl_invalid_value_falls_back_and_is_bounded(monkeypatch, raw_value, expected):
    monkeypatch.setenv("NODE_CONFIG_WRITE_SCOPE_MAX_AGE_SECONDS", raw_value)

    assert config_write_scope._max_age_seconds() == expected


def test_dedicated_signing_key_rotation_accepts_configured_fallback(monkeypatch):
    monkeypatch.setenv("NODE_CONFIG_WRITE_SIGNING_KEY", "old-key")
    token = config_write_scope.build_config_write_scope("log", "update", {"id": "rotating"})
    monkeypatch.setenv("NODE_CONFIG_WRITE_SIGNING_KEY", "new-key")
    monkeypatch.setenv("NODE_CONFIG_WRITE_SIGNING_KEY_FALLBACKS", '["old-key"]')

    source_app, payload = config_write_scope.verify_config_write_scope(token, "update")

    assert source_app == "log"
    assert payload == {"id": "rotating"}


def test_dedicated_signing_key_rotation_old_replica_accepts_future_key(monkeypatch):
    monkeypatch.setenv("NODE_CONFIG_WRITE_SIGNING_KEY", "new-key")
    token = config_write_scope.build_config_write_scope("monitor", "delete", {"ids": ["rotating"]})
    monkeypatch.setenv("NODE_CONFIG_WRITE_SIGNING_KEY", "old-key")
    monkeypatch.setenv("NODE_CONFIG_WRITE_SIGNING_KEY_FALLBACKS", '["new-key"]')

    source_app, payload = config_write_scope.verify_config_write_scope(token, "delete")

    assert source_app == "monitor"
    assert payload == {"ids": ["rotating"]}
