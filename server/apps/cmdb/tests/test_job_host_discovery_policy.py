"""JOB 主机发现准入：通过有效采集目录验证用户可用入口。"""

import pytest

from apps.cmdb.services.collect_object_tree import get_collect_obj_tree


@pytest.mark.parametrize(
    "entry_id, expected",
    [
        ("nginx", True),
        ("redis", True),
        ("docker", True),
        ("physcial_server", True),
        ("host", False),
        ("config_file", False),
        ("physcial_server_ipmi", False),
        ("network", False),
    ],
)
def test_directory_exposes_host_discovery_only_for_supported_jobs(entry_id, expected):
    entries = {child["id"]: child for group in get_collect_obj_tree() for child in group.get("children", [])}
    assert entries[entry_id]["supports_host_discovery"] is expected
