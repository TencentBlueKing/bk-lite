import json
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf"

PLUGIN_PATHS = {
    "host": PLUGIN_ROOT / "host" / "os",
    "windows_wmi": PLUGIN_ROOT / "http" / "windows_wmi",
    "host_remote": PLUGIN_ROOT / "http" / "host",
}

DEFAULT_EXCLUDE_FSTYPES = "tmpfs,devtmpfs,devfs,iso9660,overlay,aufs,squashfs,vfat,exfat,fat,fat32"
API_MONITOR_PATH = Path(__file__).resolve().parents[4] / "agents" / "stargazer" / "api" / "monitor.py"


def _disk_metrics(plugin_path: Path) -> list[dict]:
    metrics = json.loads((plugin_path / "metrics.json").read_text())
    return [metric for metric in metrics["metrics"] if metric["metric_group"] == "Disk"]


def test_all_host_templates_expose_fstype_allow_and_deny_lists():
    for plugin_path in PLUGIN_PATHS.values():
        ui = json.loads((plugin_path / "UI.json").read_text())
        fields = {field["name"] for field in ui["form_fields"]}
        template_text = "\n".join(path.read_text() for path in plugin_path.glob("*.child.toml.j2"))

        assert {"disk_include_fstypes", "disk_exclude_fstypes"} <= fields
        assert "disk_include_fstypes" in template_text
        assert "disk_exclude_fstypes" in template_text


def test_host_telegraf_template_filters_only_disk_measurements_by_fstype():
    template = (PLUGIN_PATHS["host"] / "disk.child.toml.j2").read_text()

    assert "ignore_fs" not in template
    assert "[[processors.starlark]]" in template
    assert 'namepass = ["disk"]' in template
    assert 'metric.tags.get("fstype", "")' in template
    assert "return None" in template


def test_all_disk_metrics_keep_path_and_fstype_dimensions():
    for plugin_path in PLUGIN_PATHS.values():
        for metric in _disk_metrics(plugin_path):
            dimensions = {dimension["name"] for dimension in metric["dimensions"]}
            assert {"path", "fstype"} <= dimensions, metric["name"]


def test_host_disk_aggregation_keeps_path_and_fstype():
    for metric in _disk_metrics(PLUGIN_PATHS["host"]):
        assert "by (instance_id, device, path, fstype)" in metric["query"], metric["name"]


def test_all_host_disk_configs_default_exclude_usb_filesystems_and_explain_filtering():
    for plugin_path in PLUGIN_PATHS.values():
        ui = json.loads((plugin_path / "UI.json").read_text())
        fields = {field["name"]: field for field in ui["form_fields"]}
        template_text = "\n".join(path.read_text() for path in plugin_path.glob("*.child.toml.j2"))

        exclude_types = set(fields["disk_exclude_fstypes"]["default_value"].split(","))
        assert DEFAULT_EXCLUDE_FSTYPES.split(",") == fields["disk_exclude_fstypes"]["default_value"].split(",")
        assert {"vfat", "exfat", "fat", "fat32"} <= exclude_types
        assert "ntfs" not in exclude_types
        assert fields["disk_include_fstypes"]["tooltip"]
        assert fields["disk_exclude_fstypes"]["tooltip"]
        assert DEFAULT_EXCLUDE_FSTYPES in template_text
        assert f"disk_exclude_fstypes | default('{DEFAULT_EXCLUDE_FSTYPES}')" in template_text
        assert f"disk_exclude_fstypes | default('{DEFAULT_EXCLUDE_FSTYPES}', true)" not in template_text

    assert API_MONITOR_PATH.read_text().count(DEFAULT_EXCLUDE_FSTYPES) == 2


if __name__ == "__main__":
    test_all_host_templates_expose_fstype_allow_and_deny_lists()
    test_host_telegraf_template_filters_only_disk_measurements_by_fstype()
    test_all_disk_metrics_keep_path_and_fstype_dimensions()
    test_host_disk_aggregation_keeps_path_and_fstype()
    test_all_host_disk_configs_default_exclude_usb_filesystems_and_explain_filtering()
