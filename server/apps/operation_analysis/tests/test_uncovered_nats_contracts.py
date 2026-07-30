"""补齐运维分析模块目录的 NATS 公共契约。"""

import pytest

from apps.operation_analysis.constants.constants import (
    PERMISSION_DATASOURCE,
    PERMISSION_DIRECTORY,
)
from apps.operation_analysis.nats.nats import (
    get_operation_analysis_module_list,
)


pytestmark = pytest.mark.unit


def test_operation_analysis_module_list_exposes_supported_resources():
    modules = get_operation_analysis_module_list()

    assert modules[0]["name"] == PERMISSION_DIRECTORY
    assert [item["name"] for item in modules[0]["children"]] == [
        "dashboard",
        "topology",
        "architecture",
    ]
    assert modules[1] == {
        "name": PERMISSION_DATASOURCE,
        "display_name": "数据源",
        "children": [],
    }
