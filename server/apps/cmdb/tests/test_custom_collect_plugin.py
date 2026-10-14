from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.cmdb.models.change_record import ChangeRecord
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.custom_collect_plugin import CustomCollectPlugin
from apps.cmdb.serializers.custom_collect_plugin import CustomCollectPluginSerializer
from apps.cmdb.services.custom_collect_plugin import ensure_deletable, ensure_model_deletable, validate_plugin_payload
from apps.core.exceptions.base_app_exception import BaseAppException

SCRIPT = '#!/bin/bash\necho \'[{"inst_name":"demo"}]\'\n'


def _payload(**overrides):
    data = {
        "name": "自定义主机",
        "plugin_id": "custom_host_scan",
        "model_id": "host",
        "os_type": "linux",
        "shell": "bash",
        "content": SCRIPT,
        "team": [1],
    }
    data.update(overrides)
    return data


def _request():
    return SimpleNamespace(user=SimpleNamespace(username="alice", group_list=[{"id": 1, "name": "org-a"}], is_superuser=False), COOKIES={})


def test_plugin_id_suffix_is_prefixed_by_server():
    with pytest.raises(BaseAppException, match="插件标识"):
        validate_plugin_payload(_payload(plugin_id="a"))
    with pytest.raises(BaseAppException, match="插件标识"):
        validate_plugin_payload(_payload(plugin_id=""))


@pytest.mark.django_db
def test_plugin_id_without_prefix_is_stored_with_custom_prefix():
    created = validate_plugin_payload(_payload(plugin_id="host_scan"))
    assert created["plugin_id"] == "custom_host_scan"
    again = validate_plugin_payload(_payload(plugin_id="custom_host_scan"))
    assert again["plugin_id"] == "custom_host_scan"


@pytest.mark.django_db
def test_plugin_id_collision_hides_owner():
    CustomCollectPlugin.objects.create(**validate_plugin_payload(_payload()))
    with pytest.raises(BaseAppException, match="标识已被占用"):
        validate_plugin_payload(_payload(name="另一份", team=[2]))


def test_shell_must_match_os_and_script_has_size_limit():
    with pytest.raises(BaseAppException, match="解释器"):
        validate_plugin_payload(_payload(os_type="windows", shell="bash"))
    with pytest.raises(BaseAppException, match="64KB"):
        validate_plugin_payload(_payload(content="a" * (64 * 1024 + 1)))


@pytest.mark.django_db
def test_content_change_bumps_version_and_audit_snapshot_omits_script():
    created = validate_plugin_payload(_payload())
    plugin = CustomCollectPlugin.objects.create(**created)
    assert plugin.version == 1
    assert plugin.content_checksum.startswith("sha256:")
    assert "content" not in plugin.audit_snapshot()
    assert SCRIPT not in str(plugin.audit_snapshot())

    updated = validate_plugin_payload(_payload(content=SCRIPT + "\n"), instance=plugin)
    assert updated["version"] == 2
    assert updated["content_checksum"] != plugin.content_checksum


@pytest.mark.django_db
def test_referenced_plugin_locks_model_os_and_cannot_delete():
    plugin = CustomCollectPlugin.objects.create(**validate_plugin_payload(_payload()))
    CollectModels.objects.create(
        name="host-custom",
        model_id="host",
        driver_type="job",
        task_type="custom_script",
        cycle_value_type="cycle",
        params={"custom_plugin_pk": plugin.id},
    )
    with pytest.raises(BaseAppException, match="操作系统"):
        validate_plugin_payload(_payload(os_type="windows", shell="powershell"), instance=plugin)
    with pytest.raises(BaseAppException, match="目标模型"):
        validate_plugin_payload(_payload(model_id="nginx"), instance=plugin)
    with pytest.raises(BaseAppException, match="引用"):
        ensure_deletable(plugin)
    with pytest.raises(BaseAppException, match="自定义采集插件"):
        ensure_model_deletable("host")
    ensure_model_deletable("nginx")


@pytest.mark.django_db
def test_serializer_persists_checksum_without_accepting_client_version(monkeypatch):
    monkeypatch.setattr("apps.core.utils.serializers.User.objects.filter", lambda *args, **kwargs: SimpleNamespace(values=lambda *a, **k: []))
    serializer = CustomCollectPluginSerializer(data=_payload(version=99, content_checksum="sha256:forged"), context={"request": _request()})
    assert serializer.is_valid(), serializer.errors
    plugin = serializer.save()
    assert plugin.version == 1
    assert plugin.content_checksum != "sha256:forged"
    assert not ChangeRecord.objects.filter(message__contains=SCRIPT).exists()


@pytest.mark.django_db
def test_serializer_rejects_invalid_plugin(monkeypatch):
    monkeypatch.setattr("apps.core.utils.serializers.User.objects.filter", lambda *args, **kwargs: SimpleNamespace(values=lambda *a, **k: []))
    serializer = CustomCollectPluginSerializer(data=_payload(plugin_id="a"), context={"request": _request()})
    with pytest.raises(ValidationError):
        serializer.is_valid(raise_exception=True)
