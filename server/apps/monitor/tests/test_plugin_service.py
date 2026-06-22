import copy
import importlib.util
import json
import logging
import sys
import types
from pathlib import Path

import pytest


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def test_extract_monitor_object_names_supports_basic_and_compound(monkeypatch):
    _install_module(monkeypatch, "django")
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace(atomic=lambda: None))
    _install_module(monkeypatch, "apps")
    _install_module(monkeypatch, "apps.monitor")
    _install_module(monkeypatch, "apps.monitor.constants")
    _install_module(monkeypatch, "apps.monitor.constants.database", DatabaseConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorPlugin=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
        MonitorPluginUITemplate=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
    )
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", MetricGroup=object, Metric=object)
    _install_module(monkeypatch, "apps.monitor.models.monitor_object", MonitorObject=object, MonitorObjectType=object)
    _install_module(monkeypatch, "apps.monitor.utils")
    _install_module(monkeypatch, "apps.monitor.utils.display_fields_seed", build_seed_display_fields=lambda *args, **kwargs: [])
    _install_module(monkeypatch, "apps.monitor.utils.node_selector", normalize_node_selector=lambda value=None: value or {})
    _install_module(
        monkeypatch,
        "apps.monitor.utils.instance_id_keys",
        resolve_metric_instance_id_keys=lambda *args, **kwargs: [],
        resolve_monitor_object_instance_id_keys=lambda keys, **kwargs: keys or ["instance_id"],
    )

    plugin_module = _load_module(
        "monitor_plugin_service_test_module",
        Path(__file__).resolve().parents[1] / "services" / "plugin.py",
    )

    basic_names = plugin_module.MonitorPluginService._extract_monitor_object_names({"plugin": "OceanStor", "name": "Storage"})
    compound_names = plugin_module.MonitorPluginService._extract_monitor_object_names(
        {
            "plugin": "OceanStor",
            "is_compound_object": True,
            "objects": [{"name": "Storage"}, {"name": "StoragePool"}],
        }
    )

    assert basic_names == ["Storage"]
    assert compound_names == ["Storage", "StoragePool"]


def test_sync_plugin_monitor_objects_replaces_stale_relations(monkeypatch):
    _install_module(monkeypatch, "django")
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace(atomic=lambda: None))
    _install_module(monkeypatch, "apps")
    _install_module(monkeypatch, "apps.monitor")
    _install_module(monkeypatch, "apps.monitor.constants")
    _install_module(monkeypatch, "apps.monitor.constants.database", DatabaseConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorPlugin=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
        MonitorPluginUITemplate=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
    )
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", MetricGroup=object, Metric=object)
    _install_module(monkeypatch, "apps.monitor.utils")
    _install_module(monkeypatch, "apps.monitor.utils.display_fields_seed", build_seed_display_fields=lambda *args, **kwargs: [])
    _install_module(monkeypatch, "apps.monitor.utils.node_selector", normalize_node_selector=lambda value=None: value or {})
    _install_module(
        monkeypatch,
        "apps.monitor.utils.instance_id_keys",
        resolve_metric_instance_id_keys=lambda *args, **kwargs: [],
        resolve_monitor_object_instance_id_keys=lambda keys, **kwargs: keys or ["instance_id"],
    )

    class StubMonitorObjectManager:
        def __init__(self):
            self.filter_kwargs = None

        def filter(self, **kwargs):
            self.filter_kwargs = kwargs
            return [types.SimpleNamespace(name="Storage")]

    class StubPluginRelation:
        def __init__(self):
            self.received = None

        def set(self, objs):
            self.received = list(objs)

    relation = StubPluginRelation()
    plugin_obj = types.SimpleNamespace(monitor_object=relation)

    class StubMonitorPluginManager:
        def __init__(self):
            self.filter_kwargs = None

        def filter(self, **kwargs):
            self.filter_kwargs = kwargs
            return types.SimpleNamespace(first=lambda: plugin_obj)

    monitor_object_manager = StubMonitorObjectManager()
    monitor_plugin_manager = StubMonitorPluginManager()

    _install_module(
        monkeypatch,
        "apps.monitor.models.monitor_object",
        MonitorObject=types.SimpleNamespace(objects=monitor_object_manager),
        MonitorObjectType=object,
    )

    plugin_module = _load_module(
        "monitor_plugin_service_sync_test_module",
        Path(__file__).resolve().parents[1] / "services" / "plugin.py",
    )
    plugin_module.MonitorPlugin = types.SimpleNamespace(objects=monitor_plugin_manager)
    plugin_module.MonitorObject = types.SimpleNamespace(objects=monitor_object_manager)

    plugin_module.MonitorPluginService._sync_plugin_monitor_objects("OceanStor", ["Storage"])

    assert monitor_plugin_manager.filter_kwargs == {"name": "OceanStor"}
    assert monitor_object_manager.filter_kwargs == {"name__in": ["Storage"]}
    assert [obj.name for obj in relation.received] == ["Storage"]


def test_extract_monitor_object_names_ignores_node_selector(monkeypatch):
    _install_module(monkeypatch, "django")
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace(atomic=lambda: None))
    _install_module(monkeypatch, "apps")
    _install_module(monkeypatch, "apps.monitor")
    _install_module(monkeypatch, "apps.monitor.constants")
    _install_module(monkeypatch, "apps.monitor.constants.database", DatabaseConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorPlugin=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
        MonitorPluginUITemplate=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
    )
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", MetricGroup=object, Metric=object)
    _install_module(monkeypatch, "apps.monitor.models.monitor_object", MonitorObject=object, MonitorObjectType=object)
    _install_module(monkeypatch, "apps.monitor.utils")
    _install_module(monkeypatch, "apps.monitor.utils.display_fields_seed", build_seed_display_fields=lambda *args, **kwargs: [])
    _install_module(monkeypatch, "apps.monitor.utils.node_selector", normalize_node_selector=lambda value=None: value or {})
    _install_module(
        monkeypatch,
        "apps.monitor.utils.instance_id_keys",
        resolve_metric_instance_id_keys=lambda *args, **kwargs: [],
        resolve_monitor_object_instance_id_keys=lambda keys, **kwargs: keys or ["instance_id"],
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.node_selector",
        normalize_node_selector=lambda value: value or {},
    )

    plugin_module = _load_module(
        "monitor_plugin_service_node_selector_test_module",
        Path(__file__).resolve().parents[1] / "services" / "plugin.py",
    )

    names = plugin_module.MonitorPluginService._extract_monitor_object_names(
        {"plugin": "Docker", "name": "Docker", "node_selector": {"is_container": True}}
    )

    assert names == ["Docker"]


def test_import_compound_monitor_object_propagates_node_selector(monkeypatch):
    _install_module(monkeypatch, "django")
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace(atomic=lambda: None))
    _install_module(monkeypatch, "apps")
    _install_module(monkeypatch, "apps.monitor")
    _install_module(monkeypatch, "apps.monitor.constants")
    _install_module(monkeypatch, "apps.monitor.constants.database", DatabaseConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorPlugin=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
        MonitorPluginUITemplate=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
    )
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", MetricGroup=object, Metric=object)
    _install_module(monkeypatch, "apps.monitor.models.monitor_object", MonitorObject=object, MonitorObjectType=object)
    _install_module(monkeypatch, "apps.monitor.utils")
    _install_module(monkeypatch, "apps.monitor.utils.display_fields_seed", build_seed_display_fields=lambda *args, **kwargs: [])
    _install_module(monkeypatch, "apps.monitor.utils.node_selector", normalize_node_selector=lambda value=None: value or {})
    _install_module(
        monkeypatch,
        "apps.monitor.utils.instance_id_keys",
        resolve_metric_instance_id_keys=lambda *args, **kwargs: [],
        resolve_monitor_object_instance_id_keys=lambda keys, **kwargs: keys or ["instance_id"],
    )
    _install_module(
        monkeypatch,
        "apps.monitor.utils.node_selector",
        normalize_node_selector=lambda value: value or {},
    )

    plugin_module = _load_module(
        "monitor_plugin_service_compound_node_selector_test_module",
        Path(__file__).resolve().parents[1] / "services" / "plugin.py",
    )

    captured = []

    def fake_import_basic_monitor_object(data):
        captured.append(data.copy())
        if data.get("level") == "base":
            return types.SimpleNamespace(id=99)
        return types.SimpleNamespace(id=100)

    plugin_module.MonitorPluginService.import_basic_monitor_object = staticmethod(fake_import_basic_monitor_object)

    plugin_module.MonitorPluginService.import_compound_monitor_object(
        {
            "plugin": "VMWare",
            "plugin_desc": "desc",
            "status_query": "status",
            "collector": "Telegraf",
            "collect_type": "http",
            "node_selector": {"is_container": True},
            "objects": [
                {"name": "vCenter", "level": "base", "metrics": []},
                {"name": "ESXI", "level": "derivative", "metrics": []},
            ],
        }
    )

    assert len(captured) == 2
    assert captured[0]["node_selector"] == {"is_container": True}
    assert captured[1]["node_selector"] == {"is_container": True}
    assert captured[1]["parent_id"] == 99


@pytest.mark.django_db
def test_import_basic_monitor_object_uses_plugin_scoped_metric_group():
    from apps.monitor.models.monitor_metrics import Metric, MetricGroup
    from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
    from apps.monitor.models.plugin import MonitorPlugin
    from apps.monitor.services.plugin import MonitorPluginService

    monitor_object_type = MonitorObjectType.objects.create(id="host", name="Host")
    monitor_object = MonitorObject.objects.create(
        name="Host",
        display_name="Host",
        type=monitor_object_type,
        level="base",
    )

    legacy_plugin = MonitorPlugin.objects.create(
        name="Legacy Host",
        display_name="Legacy Host",
        collector="Telegraf",
        collect_type="http",
    )
    legacy_plugin.monitor_object.add(monitor_object)
    MetricGroup.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=legacy_plugin,
        name="Network",
    )

    MonitorPluginService.import_basic_monitor_object(
        {
            "plugin": "Host Remote",
            "plugin_desc": "desc",
            "collector": "Telegraf",
            "collect_type": "http",
            "name": "Host",
            "type": "host",
            "metrics": [
                {
                    "metric_group": "Network",
                    "name": "host_net_rx_bytes",
                    "display_name": "Network RX Bytes",
                    "query": "host_net_rx_bytes",
                    "unit": "bytes",
                    "data_type": "Number",
                    "description": "",
                    "dimensions": ["interface"],
                    "instance_id_keys": ["instance_id"],
                }
            ],
        }
    )

    imported_plugin = MonitorPlugin.objects.get(name="Host Remote")
    imported_metric = Metric.objects.get(name="host_net_rx_bytes", monitor_plugin=imported_plugin)

    assert MetricGroup.objects.filter(monitor_object=monitor_object, name="Network").count() == 2
    assert imported_metric.metric_group.monitor_plugin_id == imported_plugin.id


def test_normalize_instance_identity_supports_raw_and_legacy_formats():
    dimension_module = _load_module(
        "monitor_dimension_identity_test_module",
        Path(__file__).resolve().parents[1] / "utils" / "dimension.py",
    )

    normalize_instance_identity = dimension_module.normalize_instance_identity

    raw_result = normalize_instance_identity("MTVmOTFiYTM5ODZk")
    legacy_result = normalize_instance_identity("('MTVmOTFiYTM5ODZk',)")

    assert raw_result == {
        "raw_input": "MTVmOTFiYTM5ODZk",
        "logical_instance_value": "MTVmOTFiYTM5ODZk",
        "storage_instance_key": "('MTVmOTFiYTM5ODZk',)",
    }
    assert legacy_result == {
        "raw_input": "('MTVmOTFiYTM5ODZk',)",
        "logical_instance_value": "MTVmOTFiYTM5ODZk",
        "storage_instance_key": "('MTVmOTFiYTM5ODZk',)",
    }


def test_build_safe_instance_id_encodes_parts_without_label_special_chars():
    dimension_module = _load_module(
        "monitor_dimension_safe_id_test_module",
        Path(__file__).resolve().parents[1] / "utils" / "dimension.py",
    )

    result = dimension_module.build_safe_instance_id(1, " 10.0.0.12 ")

    assert result == "MToxMC4wLjAuMTI"
    assert all(char not in result for char in ":.=")

    with pytest.raises(ValueError, match="empty"):
        dimension_module.build_safe_instance_id(1, "")


def test_normalize_instance_identity_rejects_empty_value():
    dimension_module = _load_module(
        "monitor_dimension_identity_empty_test_module",
        Path(__file__).resolve().parents[1] / "utils" / "dimension.py",
    )

    with pytest.raises(ValueError, match="instance_id"):
        dimension_module.normalize_instance_identity("")

    with pytest.raises(ValueError, match="instance_id"):
        dimension_module.normalize_instance_identity(None)


def test_normalize_instance_identity_preserves_multi_dimension_tuple():
    dimension_module = _load_module(
        "monitor_dimension_identity_multi_dimension_test_module",
        Path(__file__).resolve().parents[1] / "utils" / "dimension.py",
    )

    result = dimension_module.normalize_instance_identity("('vcenter-a', 'host-3171')")

    assert result == {
        "raw_input": "('vcenter-a', 'host-3171')",
        "logical_instance_value": "vcenter-a",
        "storage_instance_key": "('vcenter-a', 'host-3171')",
    }


def _load_plugin_controller_module(monkeypatch, template_rows=None):
    """Load plugin_controller.py with all Django dependencies stubbed out."""
    from jinja2 import BaseLoader, DebugUndefined
    from jinja2 import meta
    from jinja2.sandbox import SandboxedEnvironment

    class _FakeTemplateSecurityError(ValueError):
        pass

    def _fake_build_sandboxed_env(loader=None, undefined=DebugUndefined, extra_filters=None):
        env = SandboxedEnvironment(loader=loader or BaseLoader(), undefined=undefined)
        env.globals.clear()
        if extra_filters:
            env.filters.update(extra_filters)
        return env

    def _fake_sanitize_template_context(value, max_depth=8):
        if max_depth < 0:
            return ""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): _fake_sanitize_template_context(v, max_depth - 1) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_fake_sanitize_template_context(v, max_depth - 1) for v in value]
        return str(value)

    def _fake_validate_template_variables(template_str, env, allowed_variables):
        ast = env.parse(template_str)
        unexpected = meta.find_undeclared_variables(ast) - allowed_variables
        if unexpected:
            raise _FakeTemplateSecurityError(f"模板包含未授权变量: {', '.join(sorted(unexpected))}")

    _rows = template_rows or []
    _fake_qs = types.SimpleNamespace(values=lambda *args, **kwargs: iter(_rows))
    _fake_template_model = types.SimpleNamespace(
        objects=types.SimpleNamespace(filter=lambda **kwargs: _fake_qs)
    )

    _install_module(monkeypatch, "django")
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace(atomic=lambda: None))
    _install_module(monkeypatch, "apps")
    _install_module(monkeypatch, "apps.core")
    _install_module(monkeypatch, "apps.core.exceptions")
    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install_module(monkeypatch, "apps.core.utils")
    _install_module(
        monkeypatch,
        "apps.core.utils.safe_template",
        TemplateSecurityError=_FakeTemplateSecurityError,
        build_sandboxed_env=_fake_build_sandboxed_env,
        sanitize_template_context=_fake_sanitize_template_context,
        validate_template_variables=_fake_validate_template_variables,
    )
    _install_module(monkeypatch, "apps.core.logger", monitor_logger=logging.getLogger("monitor"))
    _install_module(monkeypatch, "apps.monitor")
    _install_module(monkeypatch, "apps.monitor.constants")
    _install_module(monkeypatch, "apps.monitor.constants.database", DatabaseConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        CollectConfig=object,
        MonitorPlugin=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
        MonitorPluginConfigTemplate=_fake_template_model,
    )
    _install_module(monkeypatch, "apps.monitor.utils")
    # Intentionally naive stub: does NOT parse tuple-string format, so the test exposes
    # whether render_template correctly falls back to logical_instance_value.
    _install_module(
        monkeypatch,
        "apps.monitor.utils.dimension",
        parse_instance_id=lambda x: (x,) if x else (),
    )
    _install_module(monkeypatch, "apps.rpc")
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)

    return _load_module(
        "monitor_plugin_controller_test_module",
        Path(__file__).resolve().parents[1] / "utils" / "plugin_controller.py",
    )


def test_render_template_prefers_logical_instance_value(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    rendered = plugin_controller_module.Controller({}).render_template(
        "{{ instance_id }}",
        {
            "instance_id": "('MTVmOTFiYTM5ODZk',)",
            "logical_instance_value": "MTVmOTFiYTM5ODZk",
        },
    )

    assert rendered == "MTVmOTFiYTM5ODZk"


def test_get_templates_by_collector_keeps_monitor_plugin_id_branch(monkeypatch):
    template_rows = [
        {
            "type": "host",
            "config_type": "child",
            "file_type": "toml",
            "content": "custom-template",
        }
    ]
    plugin_controller_module = _load_plugin_controller_module(monkeypatch, template_rows=template_rows)

    templates = plugin_controller_module.Controller({"monitor_plugin_id": 208}).get_templates_by_collector("Telegraf", "http")

    assert templates == {"host": template_rows}


def test_render_template_falls_back_to_parsed_instance_id_without_logical_value(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    rendered = plugin_controller_module.Controller({}).render_template(
        "{{ instance_id }}",
        {
            "instance_id": "MTVmOTFiYTM5ODZk",
            # logical_instance_value intentionally absent
        },
    )

    assert rendered == "MTVmOTFiYTM5ODZk"


def test_render_template_supports_default_filter(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    rendered = plugin_controller_module.Controller({}).render_template(
        '{{ auth_type | default("none", true) }}',
        {"auth_type": ""},
    )

    assert rendered == "none"


def test_render_template_supports_lower_filter_for_toml_booleans(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    rendered = plugin_controller_module.Controller({}).render_template(
        "insecure_skip_verify = {{ insecure_skip_verify | default(false) | lower }}",
        {"insecure_skip_verify": False},
    )

    assert rendered == "insecure_skip_verify = false"


def test_render_template_allows_business_default_variables(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    rendered = plugin_controller_module.Controller({}).render_template(
        '{{ interval | default(60, true) }}',
        {"instance_id": "host-1"},
    )

    assert rendered == "60"


def test_render_template_blocks_unknown_template_variable(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    with pytest.raises(Exception, match="未授权变量"):
        plugin_controller_module.Controller({}).render_template(
            "{{ settings.SECRET_KEY }}",
            {"instance_id": "host-1"},
        )


def test_render_template_treats_payload_value_as_plain_text(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)
    payload = "{{ cycler.__init__.__globals__.os.popen('id').read() }}"

    rendered = plugin_controller_module.Controller({}).render_template(
        'community = "{{ community }}"',
        {
            "instance_id": "host-1",
            "community": payload,
        },
    )

    assert payload in rendered


def test_render_template_sanitizes_python_objects(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    class DangerousObject:
        secret = "should-not-render"

        def __str__(self):
            return "safe-string"

    rendered = plugin_controller_module.Controller({}).render_template(
        "{{ obj }}",
        {
            "instance_id": "host-1",
            "obj": DangerousObject(),
        },
    )

    assert rendered == "safe-string"
    assert "should-not-render" not in rendered


def test_to_toml_dict_escapes_quoted_values(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    rendered = plugin_controller_module.to_toml_dict({"safe": 'x"\nmalicious = "yes'})

    assert '\\"' in rendered
    assert "\\nmalicious" in rendered
    assert '\nmalicious = "yes"' not in rendered


def test_render_template_escapes_toml_string_values(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    rendered = plugin_controller_module.Controller({}).render_template(
        'community = "{{ community }}"',
        {
            "instance_id": "host-1",
            "community": 'public"\nmalicious = "yes',
        },
        escape_toml_strings=True,
    )

    assert 'public\\"\\nmalicious = \\"yes' in rendered
    assert '\nmalicious = "yes"' not in rendered


def test_render_template_preserves_sidecar_env_placeholders(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    rendered = plugin_controller_module.Controller({}).render_template(
        'url = "${STARGAZER_URL}/metrics"\npassword = "${PASSWORD__{{ config_id }}}"',
        {
            "instance_id": "host-1",
            "config_id": "CONFIG1",
        },
        escape_toml_strings=True,
    )

    assert '${STARGAZER_URL}/metrics' in rendered
    assert '${PASSWORD__CONFIG1}' in rendered


def test_host_remote_template_renders_ansible_executor_instance_id(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)
    template_path = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf" / "http" / "host" / "host.child.toml.j2"
    template_content = template_path.read_text()

    rendered = plugin_controller_module.Controller({}).render_template(
        template_content,
        {
            "host": "10.0.0.8",
            "username": "root",
            "password": "secret",
            "instance_id": "('MTVmOTFiYTM5ODZk',)",
            "logical_instance_value": "MTVmOTFiYTM5ODZk",
            "node_id": "node-1",
            "config_id": "CONFIG1",
            "interval": 60,
            "timeout": 60,
            "response_timeout": 60,
            "os_type": "linux",
            "port": 22,
            "metrics_modules": "cpu,mem,disk,net",
        },
    )

    assert 'ansible_node_id = "node-1"' in rendered


def test_host_remote_template_renders_winrm_and_private_key_headers(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)
    template_path = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf" / "http" / "host" / "host.child.toml.j2"
    template_content = template_path.read_text()

    rendered = plugin_controller_module.Controller({}).render_template(
        template_content,
        {
            "host": "10.0.0.8",
            "username": "Administrator",
            "instance_id": "('MTVmOTFiYTM5ODZk',)",
            "logical_instance_value": "MTVmOTFiYTM5ODZk",
            "node_id": "node-1",
            "config_id": "CONFIG1",
            "interval": 60,
            "timeout": 60,
            "response_timeout": 60,
            "os_type": "windows",
            "port": 5986,
            "metrics_modules": ["cpu", "mem", "diskio"],
            "auth_type": "password",
            "winrm_scheme": "https",
            "winrm_transport": "ntlm",
            "winrm_cert_validation": False,
        },
    )

    assert 'metrics_modules = "cpu,mem,diskio"' in rendered
    assert 'auth_type = "password"' in rendered
    assert 'password = "${PASSWORD__CONFIG1}"' in rendered
    assert 'winrm_scheme = "https"' in rendered
    assert 'winrm_transport = "ntlm"' in rendered
    assert 'winrm_cert_validation = "false"' in rendered

    private_key_rendered = plugin_controller_module.Controller({}).render_template(
        template_content,
        {
            "host": "10.0.0.9",
            "username": "root",
            "instance_id": "('MTVmOTFiYTM5ODZl',)",
            "logical_instance_value": "MTVmOTFiYTM5ODZl",
            "node_id": "node-1",
            "config_id": "CONFIG2",
            "interval": 60,
            "timeout": 60,
            "response_timeout": 60,
            "os_type": "linux",
            "port": 22,
            "metrics_modules": ["cpu", "system"],
            "auth_type": "private_key",
        },
    )

    assert 'private_key_content = "${PRIVATE_KEY_CONTENT__CONFIG2}"' in private_key_rendered
    assert 'private_key_passphrase = "${PRIVATE_KEY_PASSPHRASE__CONFIG2}"' in private_key_rendered


def test_windows_wmi_template_renders_headers(monkeypatch):
    plugin_controller_module = _load_plugin_controller_module(monkeypatch)

    template_path = (
        Path(__file__).resolve().parents[1]
        / "support-files"
        / "plugins"
        / "Telegraf"
        / "http"
        / "windows_wmi"
        / "windows_wmi.child.toml.j2"
    )
    template_content = template_path.read_text()

    rendered = plugin_controller_module.Controller({}).render_template(
        template_content,
        {
            "config_id": "cfg1",
            "host": "10.0.0.8",
            "username": "EXAMPLE\\monitor",
            "namespace": "root\\cimv2",
            "metrics_modules": ["cpu", "mem"],
            "timeout": 45,
            "interval": 60,
            "instance_id": "region_os_10.0.0.8",
            "instance_type": "os",
        },
    )

    assert 'urls = ["${STARGAZER_URL}/api/monitor/windows/wmi/metrics"]' in rendered
    assert 'host = "10.0.0.8"' in rendered
    assert 'username = "EXAMPLE\\monitor"' in rendered
    assert 'password = "${PASSWORD__cfg1}"' in rendered
    assert 'namespace = "root\\cimv2"' in rendered
    assert 'metrics_modules = "cpu,mem"' in rendered
    assert 'config_type = "windows_wmi"' in rendered


def test_host_remote_status_query_is_scoped_to_host_config_type():
    metrics_path = (
        Path(__file__).resolve().parents[1]
        / "support-files"
        / "plugins"
        / "Telegraf"
        / "http"
        / "host"
        / "metrics.json"
    )
    data = json.loads(metrics_path.read_text(encoding="utf-8"))

    assert "config_type='host'" in data["status_query"]


def test_host_remote_ui_exposes_selectable_metrics_and_credentials():
    ui_path = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf" / "http" / "host" / "UI.json"
    data = json.loads(ui_path.read_text(encoding="utf-8"))
    fields = {field["name"]: field for field in data["form_fields"]}

    assert fields["metrics_modules"]["type"] == "checkbox_group"
    assert fields["metrics_modules"]["default_value"] == ["cpu", "mem", "disk", "net"]
    metric_values = {option["value"] for option in fields["metrics_modules"]["options"]}
    assert {"cpu", "mem", "disk", "net", "diskio", "processes", "system"}.issubset(metric_values)

    assert fields["auth_type"]["type"] == "select"
    assert fields["auth_type"]["default_value"] == "password"
    assert fields["private_key_content"]["encrypted"] is True
    assert fields["private_key_passphrase"]["encrypted"] is True

    assert fields["winrm_scheme"]["default_value"] == "https"
    assert fields["winrm_transport"]["default_value"] == "ntlm"
    assert fields["winrm_cert_validation"]["default_value"] is False
    assert "Basic" in fields["winrm_transport"]["description"]


def test_controller_raises_identity_error_when_instance_value_is_invalid(monkeypatch):
    template_rows = [
        {"type": "host", "config_type": "main", "file_type": "toml", "content": "{{ instance_id }}"}
    ]
    plugin_controller_module = _load_plugin_controller_module(monkeypatch, template_rows=template_rows)

    # Simulate a genuinely unparseable instance_id: parse_instance_id returns empty tuple
    plugin_controller_module.parse_instance_id = lambda x: ()

    ctrl = plugin_controller_module.Controller({
        "collector": "Telegraf",
        "collect_type": "http",
        "instances": [{"instance_id": "unparseable-id", "node_ids": ["node1"], "type": "host"}],
        "configs": [{"type": "host"}],
    })

    with pytest.raises(Exception, match="实例识别失败"):
        ctrl.controller()


@pytest.mark.django_db
def test_import_basic_monitor_object_uses_plugin_scoped_metric_group():
    from apps.monitor.models.monitor_metrics import Metric, MetricGroup
    from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
    from apps.monitor.models.plugin import MonitorPlugin
    from apps.monitor.services.plugin import MonitorPluginService

    monitor_object_type = MonitorObjectType.objects.create(id="OS", name="OS")
    host_monitor_object = MonitorObject.objects.create(
        name="Host",
        type=monitor_object_type,
        description="Legacy host monitoring",
        default_metric="legacy_metric",
        instance_id_keys=["instance_id"],
    )
    legacy_plugin = MonitorPlugin.objects.create(
        name="Host Legacy",
        description="Legacy host metrics collection",
        collector="Telegraf",
        collect_type="http",
    )
    legacy_plugin.monitor_object.add(host_monitor_object)
    legacy_group = MetricGroup.objects.create(
        monitor_object=host_monitor_object,
        monitor_plugin=legacy_plugin,
        name="Network",
    )

    payload = {
        "plugin": "Host Remote",
        "plugin_desc": "Remote host metrics collection",
        "collector": "Telegraf",
        "collect_type": "http",
        "name": "Host",
        "type": "OS",
        "description": "Remote host monitoring",
        "default_metric": "any({instance_type='os'}) by (instance_id)",
        "instance_id_keys": ["instance_id"],
        "metrics": [
            {
                "metric_group": "Network",
                "name": "host_net_rx_bytes",
                "query": 'host_net_rx_bytes{instance_id="$instance_id"}',
                "display_name": "Network RX Bytes",
                "data_type": "Number",
                "unit": "bytes",
                "dimensions": ["interface"],
                "instance_id_keys": ["instance_id"],
                "description": "Network bytes received per interface",
            }
        ],
    }

    MonitorPluginService.import_basic_monitor_object(copy.deepcopy(payload))

    remote_plugin = MonitorPlugin.objects.get(name="Host Remote")
    remote_group_qs = MetricGroup.objects.filter(
        monitor_object=host_monitor_object,
        monitor_plugin=remote_plugin,
        name="Network",
    )
    assert remote_group_qs.exists(), "import_basic_monitor_object should create a plugin-scoped MetricGroup for the remote plugin"
    remote_group = remote_group_qs.get()
    imported_metric = Metric.objects.get(name="host_net_rx_bytes", monitor_plugin=remote_plugin)

    assert imported_metric.metric_group_id == remote_group.id
    assert imported_metric.metric_group_id != legacy_group.id
