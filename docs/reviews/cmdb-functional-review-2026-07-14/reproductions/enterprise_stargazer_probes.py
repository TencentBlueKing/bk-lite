#!/usr/bin/env python
"""F66/F67/F69 只读复现；不发网络请求、不写生产文件。"""

import argparse
import re
from pathlib import Path


def ibmmq_metric_names():
    from plugins.base_utils import convert_to_prometheus_format
    from service.collection_service import CollectionService

    rows = [
        {"object_type": "ibmmq", "qmgr_name": "QM1", "version": "9.3"},
        {"object_type": "channel", "name": "TO.REMOTE", "channel_type": "SDR"},
    ]
    wrapped = {"result": {"ibmmq": rows}, "success": True}
    service = CollectionService(
        {"model_id": "ibmmq", "plugin_name": "ibmmq_info", "executor_type": "job", "host": "192.0.2.20"}
    )
    text = convert_to_prometheus_format(service._process_result(wrapped))
    return [re.match(r"^([^\{]+)", line).group(1) for line in text.splitlines() if line and not line.startswith("#")]


def probe_f66():
    from enterprise.plugins.inputs.xsky.xsky_info import XskyInfo

    result = XskyInfo({"host": "203.0.113.254", "port": 443, "password": "wrong"}).list_all_resources()
    print(result)


def probe_f67():
    print(ibmmq_metric_names())


def probe_f67_expected_gauge_failure():
    names = ibmmq_metric_names()
    assert names == ["ibmmq_info_gauge", "ibmmq_channel_info_gauge"], names


def probe_f69():
    from core.plugin_executor import PluginExecutor
    from core.plugin_source_resolver import PluginResolution
    from core.yaml_reader import ExecutorConfig

    root = Path.cwd()
    primary = ExecutorConfig(
        "job",
        {"collector": {"module": "missing.enterprise.collector", "class": "MissingCollector"}},
        {"metadata": {"cloud_protocol": False}},
    )
    fallback = ExecutorConfig(
        "job",
        {"collector": {"module": "plugins.script_executor", "class": "SSHPlugin"}},
        {"metadata": {"cloud_protocol": False}},
    )
    resolution = PluginResolution(
        model_id="dameng",
        source="enterprise",
        plugin_path=root / "enterprise/plugins/inputs/dameng/plugin.yml",
        plugin_root=root / "enterprise/plugins/inputs/dameng",
        has_oss_fallback=True,
        fallback_plugin_path=root / "plugins/inputs/dameng/plugin.yml",
    )
    executor = PluginExecutor(
        "dameng",
        primary,
        {},
        plugin_resolution=resolution,
        fallback_executor_config=fallback,
        strict_enterprise=False,
    )
    collector = executor._load_collector_with_fallback(primary.get_collector_info())
    print(f"{collector.__module__}.{collector.__name__}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", choices=("f66", "f67", "f67_expected_gauge_failure", "f69"))
    args = parser.parse_args()
    {
        "f66": probe_f66,
        "f67": probe_f67,
        "f67_expected_gauge_failure": probe_f67_expected_gauge_failure,
        "f69": probe_f69,
    }[args.probe]()
