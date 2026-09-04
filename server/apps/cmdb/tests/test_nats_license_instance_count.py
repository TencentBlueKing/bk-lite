"""CMDB 许可用量 NATS 接口，不影响公共 model_inst_count。"""

import pytest

from apps.cmdb.nats import nats as N
from apps.cmdb.services.instance import InstanceManage


@pytest.mark.unit
def test_license_cmdb_instance_count_uses_license_counter(monkeypatch):
    monkeypatch.setattr(
        InstanceManage,
        "license_instance_count",
        classmethod(lambda cls: {"host": 4, "switch": 1}),
    )

    out = N.license_cmdb_instance_count()

    assert out == {"result": True, "message": "", "data": {"host": 4, "switch": 1}}


@pytest.mark.unit
def test_public_model_inst_count_still_counts_all_models(monkeypatch):
    monkeypatch.setattr(
        InstanceManage,
        "model_inst_count",
        classmethod(lambda cls, permissions_map, creator="": {"host": 4, "mysql": 9}),
    )

    out = N.model_inst_count()

    assert out["data"]["mysql"] == 9
    assert out["data"]["host"] == 4
