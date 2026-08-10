"""内置补丁源真实外网验收。

默认跳过，发布前显式设置 ``RUN_PATCH_SOURCE_LIVE_TESTS=1`` 运行。
每个源必须通过当前 connector 解析出真实候选，再将一条候选
写入测试数据库；pytest 事务在用例后回滚。
"""

import os
from unittest.mock import patch

import pytest

from apps.patch_mgmt.constants import OSType
from apps.patch_mgmt.models import Patch, PatchSource
from apps.patch_mgmt.services.builtin_source_service import BUILTIN_PATCH_SOURCES
from apps.patch_mgmt.services.linux_repo_sync import fetch_advisories
from apps.patch_mgmt.services.source_sync_service import SourceSyncService


pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        os.getenv("RUN_PATCH_SOURCE_LIVE_TESTS") != "1",
        reason="仅在发布前显式运行真实补丁源验收",
    ),
]


@pytest.mark.parametrize(
    "definition",
    BUILTIN_PATCH_SOURCES,
    ids=lambda definition: definition.key,
)
def test_builtin_source_connector_preview_and_temporary_ingest(definition):
    source = PatchSource.objects.create(
        builtin_key=definition.key,
        **definition.as_defaults(),
    )

    advisories = fetch_advisories(source)

    assert advisories, f"{definition.key} 未解析出任何候选补丁"
    selected = advisories[0]
    with patch(
        "apps.patch_mgmt.services.linux_repo_sync.fetch_advisories",
        return_value=advisories,
    ):
        result = SourceSyncService.ingest_selected(
            source,
            [selected.advisory_id],
            team_id=1,
        )

    assert result == {"created": 1, "updated": 0, "skipped": 0, "total": 1}
    ingested = Patch.objects.get(
        title=selected.advisory_id,
        os_type=OSType.LINUX,
    )
    assert ingested.team == [1]
    assert source in ingested.sources.all()
    assert ingested.linux_detail.pkg_name
