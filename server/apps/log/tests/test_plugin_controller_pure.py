import pydantic.root_model  # noqa

import os

from apps.log.utils.plugin_controller import Controller


# ----------------------- get_child_config_sort_order -----------------------


def test_get_child_config_sort_order_flows_is_one():
    assert Controller({}).get_child_config_sort_order("flows") == 1


def test_get_child_config_sort_order_other_is_zero():
    assert Controller({}).get_child_config_sort_order("http") == 0


# ----------------------- format_configs -----------------------


def test_format_configs_expands_nodes_and_configs():
    data = {
        "collect_type": "logfile",
        "collector": "Filebeat",
        "instances": [
            {"instance_id": "i1", "instance_name": "n1", "node_ids": ["node-a", "node-b"]},
        ],
        "configs": [{"path": "/var/log/a"}],
    }
    out = Controller(data).format_configs()
    # 1 instance * 2 nodes * 1 config = 2 条
    assert len(out) == 2
    assert out[0]["node_id"] == "node-a"
    assert out[1]["node_id"] == "node-b"
    assert out[0]["collector"] == "Filebeat"
    assert out[0]["collect_type"] == "logfile"
    assert out[0]["path"] == "/var/log/a"
    assert out[0]["instance_id"] == "i1"


def test_format_configs_multiple_configs_per_node():
    data = {
        "collect_type": "ct",
        "collector": "C",
        "instances": [{"instance_id": "i1", "node_ids": ["n1"]}],
        "configs": [{"a": 1}, {"b": 2}],
    }
    out = Controller(data).format_configs()
    assert len(out) == 2
    assert out[0]["a"] == 1
    assert out[1]["b"] == 2


# ----------------------- normalize_packetbeat_device (windows branches) -----------------------


def test_normalize_packetbeat_device_windows_empty_defaults_to_zero():
    assert Controller.normalize_packetbeat_device("", "windows") == "0"


def test_normalize_packetbeat_device_windows_keeps_multi_device():
    # windows 下多设备不会折叠成 any
    assert Controller.normalize_packetbeat_device("0,1", "windows") == "0"


def test_normalize_packetbeat_device_linux_single():
    assert Controller.normalize_packetbeat_device("eth0", "linux") == "eth0"


# ----------------------- get_template_info_by_type / has_template_for_config_type -----------------------


def test_get_template_info_by_type_parses_filenames(tmp_path):
    (tmp_path / "logfile.base.yaml.j2").write_text("x")
    (tmp_path / "logfile.child.toml.j2").write_text("y")
    (tmp_path / "other.base.yaml.j2").write_text("z")  # 类型不匹配
    (tmp_path / "bad_name.j2").write_text("w")  # 非法命名（少于3段）
    (tmp_path / "ignore.txt").write_text("t")  # 非 j2

    result = Controller({}).get_template_info_by_type(str(tmp_path), "logfile")
    found = {(r["config_type"], r["file_type"]) for r in result}
    assert found == {("base", "yaml"), ("child", "toml")}
    assert all(r["type"] == "logfile" for r in result)


def test_has_template_for_config_type_true_and_false(tmp_path, mocker):
    (tmp_path / "logfile.base.yaml.j2").write_text("x")
    mocker.patch(
        "apps.log.utils.plugin_controller.PluginConstants.DIRECTORY", str(tmp_path)
    )
    # render_config 拼接路径 DIRECTORY/collector/collect_type，需要构造对应目录
    plugin_dir = tmp_path / "Filebeat" / "logfile"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "logfile.base.yaml.j2").write_text("x")

    ctrl = Controller({"collector": "Filebeat", "collect_type": "logfile"})
    assert ctrl.has_template_for_config_type("base") is True
    assert ctrl.has_template_for_config_type("child") is False
