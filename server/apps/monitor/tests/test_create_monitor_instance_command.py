"""create_monitor_instance 管理命令规格测试。"""

import yaml
import pytest
from django.core.management import call_command, CommandError

from apps.monitor.management.commands.create_monitor_instance import Command
from apps.monitor.models import CollectConfig, MonitorInstanceOrganization
from apps.monitor.models.monitor_object import MonitorObject, MonitorInstance
from apps.monitor.models.plugin import MonitorPlugin

pytestmark = pytest.mark.django_db


def _write_yaml(tmp_path, data):
    p = tmp_path / "req.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return str(p)


def _valid_request():
    return {
        "monitor_object_id": 1,
        "collector": "Telegraf",
        "collect_type": "snmp",
        "configs": [{"type": "base"}],
        "instances": [{"instance_name": "host-1", "group_ids": [1]}],
    }


class TestLoadAndValidate:
    def test_missing_file(self, tmp_path):
        with pytest.raises(CommandError):
            call_command("create_monitor_instance", "--config", str(tmp_path / "nope.yaml"),
                         "--output", str(tmp_path / "out.yaml"))

    def test_missing_required_fields(self, tmp_path):
        cfg = _write_yaml(tmp_path, {"monitor_object_id": 1})
        with pytest.raises(CommandError):
            call_command("create_monitor_instance", "--config", cfg, "--output", str(tmp_path / "o.yaml"))

    def test_configs_must_be_nonempty_list(self, tmp_path):
        data = _valid_request()
        data["configs"] = []
        cfg = _write_yaml(tmp_path, data)
        with pytest.raises(CommandError):
            call_command("create_monitor_instance", "--config", cfg, "--output", str(tmp_path / "o.yaml"))

    def test_instance_missing_field(self, tmp_path):
        data = _valid_request()
        data["instances"] = [{"instance_name": "x"}]  # 缺 group_ids
        cfg = _write_yaml(tmp_path, data)
        with pytest.raises(CommandError):
            call_command("create_monitor_instance", "--config", cfg, "--output", str(tmp_path / "o.yaml"))

    def test_config_type_required(self, tmp_path):
        data = _valid_request()
        data["configs"] = [{"foo": "bar"}]
        cfg = _write_yaml(tmp_path, data)
        with pytest.raises(CommandError):
            call_command("create_monitor_instance", "--config", cfg, "--output", str(tmp_path / "o.yaml"))


class TestGenerateInstanceId:
    def test_deterministic_from_name(self):
        cmd = Command()
        id1 = cmd._generate_instance_id({"instance_name": "host-1"})
        id2 = cmd._generate_instance_id({"instance_name": "host-1"})
        assert id1 == id2 and id1.startswith("cmd_")

    def test_random_when_no_name(self):
        cmd = Command()
        id1 = cmd._generate_instance_id({"instance_name": ""})
        assert id1.startswith("cmd_")


class TestHandleSuccess:
    def test_creates_and_writes_output(self, tmp_path, mocker):
        svc = mocker.patch(
            "apps.monitor.management.commands.create_monitor_instance."
            "InstanceConfigService.create_monitor_instance_by_node_mgmt"
        )
        obj = MonitorObject.objects.create(name="CMIObj", level="base")
        plugin = MonitorPlugin.objects.create(name="CMIPlugin")
        data = _valid_request()
        data["monitor_object_id"] = obj.id
        cfg = _write_yaml(tmp_path, data)
        out_path = tmp_path / "out.yaml"

        # 预建实例以让 _build_instances_output 找到（用与命令一致的确定性 id）
        generated_id = Command()._generate_instance_id({"instance_name": "host-1"})
        inst = MonitorInstance.objects.create(id=generated_id, name="host-1", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=1)
        CollectConfig.objects.create(
            id="cmi-cfg", monitor_instance=inst, monitor_plugin=plugin,
            collector="Telegraf", collect_type="snmp", config_type="base", file_type="toml", is_child=False,
        )

        call_command("create_monitor_instance", "--config", cfg, "--output", str(out_path))
        svc.assert_called_once()
        assert out_path.exists()
        result = yaml.safe_load(out_path.read_text(encoding="utf-8"))
        assert result["result"]["status"] == "success"
        instances = result["result"]["instances"]
        assert instances[0]["instance_name"] == "host-1"
        assert instances[0]["organizations"] == [1]
        assert len(instances[0]["configs"]) == 1

    def test_service_error_becomes_command_error(self, tmp_path, mocker):
        from apps.core.exceptions.base_app_exception import BaseAppException
        mocker.patch(
            "apps.monitor.management.commands.create_monitor_instance."
            "InstanceConfigService.create_monitor_instance_by_node_mgmt",
            side_effect=BaseAppException("boom"),
        )
        obj = MonitorObject.objects.create(name="CMIObj2", level="base")
        data = _valid_request()
        data["monitor_object_id"] = obj.id
        cfg = _write_yaml(tmp_path, data)
        with pytest.raises(CommandError):
            call_command("create_monitor_instance", "--config", cfg, "--output", str(tmp_path / "o.yaml"))
