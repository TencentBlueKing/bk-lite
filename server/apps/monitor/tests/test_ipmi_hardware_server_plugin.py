import json
import os
from pathlib import Path
import re
import subprocess
import tomllib

import pytest
import yaml
from jinja2 import Template


PLUGIN_DIR = (
    Path(__file__).resolve().parents[1]
    / "support-files"
    / "plugins"
    / "Telegraf"
    / "ipmi"
    / "hardware_server"
)


@pytest.fixture(scope="module")
def metrics():
    return json.loads((PLUGIN_DIR / "metrics.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def toml_text():
    return (PLUGIN_DIR / "hardware_server.child.toml.j2").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def normalizer_source():
    return (PLUGIN_DIR / "ipmi_normalizer.star").read_text(encoding="utf-8")


@pytest.fixture(scope="module", params=["zh-Hans.yaml", "en.yaml"])
def language(request):
    return yaml.safe_load((PLUGIN_DIR / "language" / request.param).read_text(encoding="utf-8"))


class FakeMetric:
    """以生产脚本的公开输入输出形状执行 Python/Starlark 公共语法子集。"""

    def __init__(self, name, tags=None, fields=None, time=0):
        self.name = name
        self.fields = fields or {}
        self.tags = tags or {}
        self.time = time


def _normalizer(source):
    # Telegraf 的公开构造器仅接收 measurement name，字段和标签需后续赋值。
    namespace = {"Metric": lambda name: FakeMetric(name)}
    exec(source, namespace)
    return namespace["apply"]


def _chassis_power_command(toml_text):
    match = re.search(r'commands = \[("(?:[^"\\]|\\.)*")\]', toml_text)
    assert match
    return json.loads(match.group(1))


def _psu_metric(metrics):
    matches = [metric for metric in metrics["metrics"] if metric["name"] == "ipmi_psu_status"]
    assert len(matches) == 1
    return matches[0]


def _metric_by_name(metrics, name):
    matches = [metric for metric in metrics["metrics"] if metric["name"] == name]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.unit
def test_normalizer_preserves_raw_metric_and_emits_psu_status(normalizer_source):
    raw = FakeMetric(
        "ipmi_sensor",
        fields={"status": 1},
        tags={"name": "PSU1_Status", "unit": "discrete"},
        time=123,
    )

    output = _normalizer(normalizer_source)(raw)

    assert output[0] is raw
    assert len(output) == 2
    assert output[1].name == "ipmi_psu"
    assert output[1].fields == {"status": 1, "state": -1}
    assert output[1].tags["component_id"] == "psu_1"
    assert output[1].tags["raw_name"] == "PSU1_Status"
    assert output[1].tags["profile"] == "generic"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_name", "unit", "expected_name", "expected_field", "expected_tags"),
    [
        ("PSU1_HS_Temp", "degrees_c", "ipmi_psu_temperature", "celsius", {"component_id": "psu_1", "sensor_id": "heatsink"}),
        ("PSU1_PIn", "watts", "ipmi_psu_power", "watts", {"component_id": "psu_1", "direction": "input"}),
        ("PSU2_VOut", "volts", "ipmi_psu_voltage", "volts", {"component_id": "psu_2", "direction": "output"}),
        ("PSU2_FanSpeed", "rpm", "ipmi_psu_fan_speed", "rpm", {"component_id": "psu_2", "sensor_id": "fan"}),
        ("PSU_Inlet_Temp", "degrees_c", "ipmi_psu_temperature", "celsius", {"component_id": "psu", "sensor_id": "inlet"}),
    ],
)
def test_normalizer_classifies_psu_numeric_sensors(
    normalizer_source, raw_name, unit, expected_name, expected_field, expected_tags
):
    raw = FakeMetric(
        "ipmi_sensor",
        fields={"value": 42.5, "status": 1},
        tags={"name": raw_name, "unit": unit},
    )

    output = _normalizer(normalizer_source)(raw)

    assert output[0] is raw
    assert len(output) == 2
    normalized = output[1]
    assert normalized.name == expected_name
    assert normalized.fields == {expected_field: 42.5}
    for key, value in expected_tags.items():
        assert normalized.tags[key] == value


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_name", "unit", "fields", "expected_name", "expected_fields", "expected_tags"),
    [
        ("CPU0_Status", "discrete", {"status": 1}, "ipmi_cpu", {"status": 1, "state": -1}, {"component_id": "cpu_0"}),
        ("CPU 2 Temp", "degrees_c", {"value": 51.0, "status": 1}, "ipmi_cpu_temperature", {"celsius": 51.0}, {"component_id": "cpu_2", "sensor_id": "temperature"}),
        ("CPU0_VR_Temp", "degrees_c", {"value": 70.0, "status": 1}, "ipmi_cpu_temperature", {"celsius": 70.0}, {"component_id": "cpu_0", "sensor_id": "vr"}),
        ("CPU Power", "watts", {"value": 108.0, "status": 1}, "ipmi_cpu_power", {"watts": 108.0}, {"component_id": "cpu"}),
        ("P0_VDDCR_CPU", "volts", {"value": 1.11, "status": 1}, "ipmi_cpu_voltage", {"volts": 1.11}, {"component_id": "cpu_0", "sensor_id": "vddcr"}),
        ("CPU Utilization", "percent", {"value": 35.0, "status": 1}, "ipmi_cpu_utilization", {"percent": 35.0}, {"component_id": "cpu"}),
        ("DIMM 3", "discrete", {"status": 1}, "ipmi_memory", {"status": 1, "state": -1}, {"component_id": "dimm_3", "slot": "3"}),
        ("DIMM 3 Temp", "degrees_c", {"value": 25.0, "status": 1}, "ipmi_memory_temperature", {"celsius": 25.0}, {"component_id": "dimm_3", "slot": "3"}),
        ("CPU0_A1_Temp", "degrees_c", {"value": 46.0, "status": 1}, "ipmi_memory_temperature", {"celsius": 46.0}, {"component_id": "dimm_cpu0_a1", "slot": "CPU0_A1"}),
        ("CPU0_A0_Status", "discrete", {"value": 64, "status": 1}, "ipmi_memory", {"status": 1, "state": -1, "raw_state_code": 64}, {"component_id": "dimm_cpu0_a0", "slot": "CPU0_A0"}),
        ("MEM_Power", "watts", {"value": 52.0, "status": 1}, "ipmi_memory_power", {"watts": 52.0}, {"component_id": "memory"}),
    ],
)
def test_normalizer_classifies_cpu_and_memory_sensors(
    normalizer_source, raw_name, unit, fields, expected_name, expected_fields, expected_tags
):
    raw = FakeMetric("ipmi_sensor", fields=fields, tags={"name": raw_name, "unit": unit})

    output = _normalizer(normalizer_source)(raw)

    assert output[0] is raw
    normalized = output[1]
    assert normalized.name == expected_name
    assert normalized.fields == expected_fields
    for key, value in expected_tags.items():
        assert normalized.tags[key] == value


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_name", "unit", "fields", "expected_name", "expected_fields", "expected_tags"),
    [
        ("Drive 3", "discrete", {"value": 129, "status": 1}, "ipmi_disk", {"status": -1, "state": -1, "raw_state_code": 129}, {"component_id": "drive_3", "slot": "3"}),
        ("BPDISK1_Status", "discrete", {"status": 0}, "ipmi_disk", {"status": 0, "state": -1}, {"component_id": "drive_1", "slot": "1"}),
        ("Raid0_Temp", "degrees_c", {"value": 90.0, "status": 1}, "ipmi_raid_temperature", {"celsius": 90.0}, {"component_id": "raid_0"}),
        ("RAID_BBU_Temp", "degrees_c", {"value": 31.0, "status": 1}, "ipmi_raid_battery_temperature", {"celsius": 31.0}, {"component_id": "raid", "battery_id": "bbu"}),
        ("RAID Card 1", "discrete", {"status": 1}, "ipmi_raid", {"status": -1, "state": -1}, {"component_id": "raid_1"}),
        ("FAN3_Speed", "rpm", {"value": 3528.0, "status": 1}, "ipmi_fan_component_speed", {"rpm": 3528.0}, {"component_id": "fan_3", "sensor_id": "fan"}),
        ("Fan 2 Rear Tach", "rpm", {"value": 5325.0, "status": 1}, "ipmi_fan_component_speed", {"rpm": 5325.0}, {"component_id": "fan_2", "sensor_id": "rear"}),
        ("FAN1_Present", "discrete", {"status": 1}, "ipmi_fan", {"status": -1, "state": -1}, {"component_id": "fan_1"}),
        ("FAN_Power", "watts", {"value": 8.0, "status": 1}, "ipmi_fan_power", {"watts": 8.0}, {"component_id": "fan"}),
        ("Front_HDD_Power", "watts", {"value": 5.0, "status": 1}, "ipmi_disk_power", {"watts": 5.0}, {"component_id": "disk_front", "location": "front"}),
        ("Exhaust Temp", "degrees_c", {"value": 27.0, "status": 1}, "ipmi_chassis_temperature", {"celsius": 27.0}, {"component_id": "chassis", "location": "exhaust"}),
        ("Air Flow", "cfm", {"value": 46.0, "status": 1}, "ipmi_chassis_airflow", {"cfm": 46.0}, {"component_id": "chassis"}),
        ("System Power", "watts", {"value": 532.0, "status": 1}, "ipmi_chassis_power", {"watts": 532.0}, {"component_id": "chassis"}),
    ],
)
def test_normalizer_classifies_storage_fan_and_chassis_sensors(
    normalizer_source, raw_name, unit, fields, expected_name, expected_fields, expected_tags
):
    raw = FakeMetric("ipmi_sensor", fields=fields, tags={"name": raw_name, "unit": unit})

    output = _normalizer(normalizer_source)(raw)

    assert output[0] is raw
    normalized = output[1]
    assert normalized.name == expected_name
    assert normalized.fields == expected_fields
    for key, value in expected_tags.items():
        assert normalized.tags[key] == value


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_name", "unit", "fields"),
    [
        ("BP 1 Status", "discrete", {"value": 4, "status": 1}),
        ("BP_FR_Temp", "degrees_c", {"value": 20.0, "status": 1}),
        ("BP_REAR_Temp", "discrete", {"status": 0}),
        ("Rear BP Status", "discrete", {"value": 0, "status": 1}),
    ],
)
def test_normalizer_keeps_backplane_sensors_raw(normalizer_source, raw_name, unit, fields):
    raw = FakeMetric("ipmi_sensor", fields=fields, tags={"name": raw_name, "unit": unit})

    output = _normalizer(normalizer_source)(raw)

    assert output is raw


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ipmitool_output", "exit_code", "expected_state"),
    [
        ("Chassis Power is on", 0, 1),
        ("Chassis Power is off", 0, 0),
        ("Unsupported command", 1, -1),
        ("Unexpected response", 0, -1),
    ],
)
def test_chassis_power_command_emits_numeric_state(
    toml_text, tmp_path, ipmitool_output, exit_code, expected_state
):
    fake_ipmitool = tmp_path / "ipmitool"
    fake_ipmitool.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$FAKE_IPMITOOL_OUTPUT\"\nexit \"$FAKE_IPMITOOL_EXIT_CODE\"\n",
        encoding="utf-8",
    )
    fake_ipmitool.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "FAKE_IPMITOOL_OUTPUT": ipmitool_output,
        "FAKE_IPMITOOL_EXIT_CODE": str(exit_code),
        "IPMI_HOST": "192.0.2.10",
        "IPMI_USER": "monitor",
        "IPMI_PROTOCOL": "lanplus",
        "IPMI_PASSWORD": "secret",
    }

    result = subprocess.run(
        ["/bin/sh", "-c", _chassis_power_command(toml_text)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout.strip() == f"ipmi_chassis_power state={expected_state}i"


@pytest.mark.unit
def test_chassis_power_command_uses_password_environment(toml_text):
    command = _chassis_power_command(toml_text)

    assert 'environment = ["IPMI_PASSWORD=${PASSWORD__{{ config_id }}}"' in toml_text
    assert 'ipmitool -I "$IPMI_PROTOCOL" -H "$IPMI_HOST" -U "$IPMI_USER" -E' in command
    assert " -P " not in command


@pytest.mark.unit
def test_rendered_telegraf_template_is_valid_toml(toml_text):
    rendered = Template(toml_text).render(
        username="monitor",
        config_id="cfg_1",
        protocol="lanplus",
        ip="192.0.2.10",
        interval=10,
        instance_id="server_1",
        instance_type="hardware_server",
    )

    parsed = tomllib.loads(rendered)

    assert len(parsed["inputs"]["ipmi_sensor"]) == 1
    assert len(parsed["inputs"]["exec"]) == 1
    assert len(parsed["processors"]["starlark"]) == 1


@pytest.mark.unit
def test_template_declares_external_normalizer_asset(toml_text):
    assert "# @bk_include_file ipmi_normalizer.star" in toml_text
    assert "def apply(metric):" not in toml_text


@pytest.mark.unit
def test_psu_status_queries_existing_ipmi_status_series(metrics):
    metric = _psu_metric(metrics)

    assert metric["metric_group"] == "PSU"
    assert metric["display_name"] == "PSU Status"
    assert metric["data_type"] == "Enum"
    assert metric["query"].startswith("ipmi_psu_status{")
    assert "instance_type='hardware_server'" in metric["query"]
    assert "name=~" not in metric["query"]


@pytest.mark.unit
def test_psu_status_preserves_sensor_name_as_dimension(metrics):
    metric = _psu_metric(metrics)

    assert [dimension["name"] for dimension in metric["dimensions"]] == [
        "component_id",
        "raw_name",
        "profile",
    ]
    assert metric["instance_id_keys"] == ["instance_id"]


@pytest.mark.unit
def test_psu_status_uses_telegraf_v1_enum_values(metrics):
    metric = _psu_metric(metrics)

    assert json.loads(metric["unit"]) == [
        {"name": "正常", "id": 1, "color": "#1ac44a"},
        {"name": "异常", "id": 0, "color": "#ff4d4f"},
        {"name": "未知", "id": -1, "color": "#8c8c8c"},
    ]


@pytest.mark.unit
def test_psu_status_is_not_a_device_level_display_field(metrics):
    _psu_metric(metrics)

    assert "ipmi_psu_status" not in metrics["supplementary_indicators"]
    displayed_metrics = {
        item["metric"]
        for field in metrics.get("display_fields", [])
        for item in field.get("metrics", [])
    }
    assert "ipmi_psu_status" not in displayed_metrics


@pytest.mark.unit
def test_psu_status_reuses_unfiltered_ipmi_sensor_collection(toml_text):
    assert "[[inputs.ipmi_sensor]]" in toml_text
    assert "power[ _-]*supply" not in toml_text


@pytest.mark.unit
def test_manifest_registers_component_metrics(metrics):
    expected_groups = {
        "ipmi_chassis_power_state": "Chassis",
        "ipmi_chassis_power_watts": "Chassis",
        "ipmi_chassis_temperature_celsius": "Chassis",
        "ipmi_chassis_airflow_cfm": "Chassis",
        "ipmi_psu_status": "PSU",
        "ipmi_psu_state": "PSU",
        "ipmi_psu_raw_state_code": "PSU",
        "ipmi_psu_temperature_celsius": "PSU",
        "ipmi_psu_power_watts": "PSU",
        "ipmi_psu_voltage_volts": "PSU",
        "ipmi_psu_fan_speed_rpm": "PSU",
        "ipmi_cpu_status": "CPU",
        "ipmi_cpu_state": "CPU",
        "ipmi_cpu_raw_state_code": "CPU",
        "ipmi_cpu_temperature_celsius": "CPU",
        "ipmi_cpu_power_watts": "CPU",
        "ipmi_cpu_voltage_volts": "CPU",
        "ipmi_cpu_utilization_percent": "CPU",
        "ipmi_memory_status": "Memory",
        "ipmi_memory_state": "Memory",
        "ipmi_memory_raw_state_code": "Memory",
        "ipmi_memory_temperature_celsius": "Memory",
        "ipmi_memory_power_watts": "Memory",
        "ipmi_disk_status": "Disk",
        "ipmi_disk_state": "Disk",
        "ipmi_disk_raw_state_code": "Disk",
        "ipmi_disk_power_watts": "Disk",
        "ipmi_raid_status": "RAID",
        "ipmi_raid_state": "RAID",
        "ipmi_raid_raw_state_code": "RAID",
        "ipmi_raid_temperature_celsius": "RAID",
        "ipmi_raid_battery_temperature_celsius": "RAID",
        "ipmi_fan_status": "Fan",
        "ipmi_fan_state": "Fan",
        "ipmi_fan_raw_state_code": "Fan",
        "ipmi_fan_component_speed_rpm": "Fan",
        "ipmi_fan_power_watts": "Fan",
    }

    for name, group in expected_groups.items():
        metric = _metric_by_name(metrics, name)
        assert metric["metric_group"] == group
        assert metric["query"].startswith(f"{name}{{")


@pytest.mark.unit
def test_manifest_does_not_register_backplane_metrics(metrics):
    assert all(metric["metric_group"] != "Backplane" for metric in metrics["metrics"])
    assert all(not metric["name"].startswith("ipmi_backplane_") for metric in metrics["metrics"])


@pytest.mark.unit
def test_legacy_raw_ipmi_metrics_remain_available(metrics):
    for name in ["ipmi_power_watts", "ipmi_voltage_volts", "ipmi_temperature_celsius"]:
        metric = _metric_by_name(metrics, name)
        assert metric["query"].startswith("ipmi_sensor_value{")


@pytest.mark.unit
def test_legacy_fan_speed_metric_keeps_raw_rpm_query(metrics):
    metric = _metric_by_name(metrics, "ipmi_fan_speed_rpm")

    assert metric["metric_group"] == "Environment"
    assert metric["query"].startswith("ipmi_sensor_value{")
    assert 'unit="rpm"' in metric["query"]
    assert metric["dimensions"] == [{"name": "name", "description": "name"}]


@pytest.mark.unit
def test_component_metrics_and_groups_have_translations(metrics, language):
    metric_translations = language["monitor_object_metric"]["Hardware Server"]
    group_translations = language["monitor_object_metric_group"]["Hardware Server"]

    for metric in metrics["metrics"]:
        assert metric["name"] in metric_translations
        assert metric["metric_group"] in group_translations


@pytest.mark.unit
def test_language_does_not_expose_backplane_group(language):
    metric_translations = language["monitor_object_metric"]["Hardware Server"]
    group_translations = language["monitor_object_metric_group"]["Hardware Server"]

    assert "Backplane" not in group_translations
    assert all(not name.startswith("ipmi_backplane_") for name in metric_translations)
