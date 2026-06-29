# -- coding: utf-8 --
"""子网录入重叠校验。规格 §3：与已有子网任一交集即拒；编辑排除自身。"""
import pytest
from unittest.mock import patch
from apps.cmdb.services.ipam_subnet import validate_subnet_no_overlap
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit

EXISTING = [
    {"_id": 1, "inst_name": "net-a", "subnet_address": "10.0.1.0", "subnet_mask": "24"},
    {"_id": 2, "inst_name": "net-b", "subnet_address": "10.0.2.0", "subnet_mask": "24"},
]


def _patch_existing(rows):
    return patch("apps.cmdb.services.ipam_subnet._query_subnet_instances", return_value=rows)


class TestSubnetOverlap:
    def test_不重叠通过(self):
        with _patch_existing(EXISTING):
            validate_subnet_no_overlap({"subnet_address": "10.0.3.0", "subnet_mask": "24"})

    def test_重叠被拒(self):
        with _patch_existing(EXISTING):
            with pytest.raises(BaseAppException) as e:
                validate_subnet_no_overlap({"subnet_address": "10.0.1.128", "subnet_mask": "25"})
            assert "net-a" in str(e.value)

    def test_编辑排除自身(self):
        with _patch_existing(EXISTING):
            validate_subnet_no_overlap({"subnet_address": "10.0.1.0", "subnet_mask": "24"}, exclude_inst_id=1)

    def test_缺地址或掩码跳过校验(self):
        with _patch_existing(EXISTING):
            validate_subnet_no_overlap({"subnet_address": "", "subnet_mask": ""})
