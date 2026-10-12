# -*- coding: utf-8 -*-
"""主机机器类型：采集值规范化，以及未知结果不覆盖已识别类型。"""
import pytest

from apps.cmdb.collection.collect_plugin.host import HostCollectMetrics
from apps.cmdb.collection.host_machine_type import normalize_machine_type, preserve_collected_host_machine_type

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("virtual", "virtual"),
        ("physical_server", "physical_server"),
        ("unknown", "unknown"),
        (" Virtual ", "virtual"),
        ("", "unknown"),
        (None, "unknown"),
        ("desktop", "unknown"),
    ],
)
def test_normalize_machine_type(raw, expected):
    assert normalize_machine_type(raw) == expected


def test_preserve_keeps_positive_type_when_collect_is_unknown():
    old_rows = [{"inst_name": "10.0.0.8", "machine_type": "physical_server"}]
    new_rows = [{"inst_name": "10.0.0.8", "machine_type": "unknown", "hostname": "srv"}]

    preserve_collected_host_machine_type(old_rows, new_rows)

    assert new_rows[0]["machine_type"] == "physical_server"
    assert new_rows[0]["hostname"] == "srv"


def test_preserve_lets_positive_detection_replace_previous_type():
    old_rows = [{"inst_name": "10.0.0.8", "machine_type": "physical_server"}]
    new_rows = [{"inst_name": "10.0.0.8", "machine_type": "virtual"}]

    preserve_collected_host_machine_type(old_rows, new_rows)

    assert new_rows[0]["machine_type"] == "virtual"


def test_preserve_writes_unknown_when_neither_side_is_identified():
    new_rows = [{"inst_name": "10.0.0.9"}]

    preserve_collected_host_machine_type([], new_rows)

    assert new_rows[0]["machine_type"] == "unknown"


@pytest.fixture
def host_runner(monkeypatch):
    monkeypatch.setattr(HostCollectMetrics, "model_id", property(lambda self: "host"))
    return HostCollectMetrics("web01", "cmdb_1", 1)


def test_host_mapping_normalizes_machine_type(host_runner):
    assert host_runner.set_machine_type({"machine_type": "physical_server"}) == "physical_server"
    assert host_runner.set_machine_type({"machine_type": "nope"}) == "unknown"
    assert host_runner.set_machine_type({}) == "unknown"
