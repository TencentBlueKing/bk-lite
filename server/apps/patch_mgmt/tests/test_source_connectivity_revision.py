"""补丁源连通性结果按配置版本条件写回。"""

import pytest

from apps.patch_mgmt.constants import ConnectivityStatus, PatchSourceType
from apps.patch_mgmt.models import PatchSource
from apps.patch_mgmt.services.connectivity_prober import ProbeResult
from apps.patch_mgmt.services.patch_source_service import PatchSourceService
from apps.patch_mgmt.services.source_sync_service import SourceSyncService
from apps.patch_mgmt.tasks import check_patch_source_connectivity


def _source(**overrides):
    values = {
        "name": "Ubuntu Repo",
        "source_type": PatchSourceType.APT_REPO,
        "url": "https://old.example.com",
        "distro_name": "ubuntu",
        "os_version": "22.04",
        "is_enabled": True,
        "team": [1],
    }
    values.update(overrides)
    return PatchSource.objects.create(**values)


@pytest.mark.django_db
class TestSourceConnectivityRevision:
    def test_stale_probe_with_old_revision_does_not_overwrite_unknown(self):
        source = _source(
            connectivity_status=ConnectivityStatus.UNKNOWN,
            connectivity_revision=1,
        )
        stale = PatchSource.objects.get(pk=source.pk)
        stale.connectivity_revision = 0

        SourceSyncService.record_connectivity_result(stale, reachable=True)

        source.refresh_from_db()
        assert source.connectivity_status == ConnectivityStatus.UNKNOWN
        assert source.connectivity_revision == 1
        assert source.last_checked_at is None

    def test_matching_revision_can_write_connected_and_failed(self):
        connected = _source(
            name="Match-Connected",
            connectivity_status=ConnectivityStatus.UNKNOWN,
            connectivity_revision=2,
        )
        failed = _source(
            name="Match-Failed",
            connectivity_status=ConnectivityStatus.UNKNOWN,
            connectivity_revision=3,
        )

        SourceSyncService.record_connectivity_result(connected, reachable=True, revision=2)
        SourceSyncService.record_connectivity_result(failed, reachable=False, revision=3)

        connected.refresh_from_db()
        failed.refresh_from_db()
        assert connected.connectivity_status == ConnectivityStatus.CONNECTED
        assert connected.last_checked_at is not None
        assert failed.connectivity_status == ConnectivityStatus.FAILED
        assert failed.last_checked_at is not None

    def test_connection_field_update_increments_revision_and_resets_unknown(self, mocker):
        source = _source(
            name="YUM-Rev",
            source_type=PatchSourceType.YUM_REPO,
            url="https://old.example.com",
            connectivity_status=ConnectivityStatus.CONNECTED,
            connectivity_revision=0,
        )
        enqueue = mocker.patch("apps.patch_mgmt.tasks.check_patch_source_connectivity.delay")

        PatchSourceService.reset_connectivity_after_config_change(source)
        check_patch_source_connectivity.delay(source.id, source.connectivity_revision)

        source.refresh_from_db()
        assert source.connectivity_status == ConnectivityStatus.UNKNOWN
        assert source.connectivity_revision == 1
        assert source.last_checked_at is None
        enqueue.assert_called_once_with(source.id, 1)

    def test_legacy_task_without_revision_is_fail_closed_when_revision_positive(self, mocker):
        source = _source(
            connectivity_status=ConnectivityStatus.UNKNOWN,
            connectivity_revision=1,
        )
        mocker.patch(
            "apps.patch_mgmt.services.connectivity_prober.probe_source",
            return_value=ProbeResult(True, 200, "ok"),
        )

        check_patch_source_connectivity(source.id)

        source.refresh_from_db()
        assert source.connectivity_status == ConnectivityStatus.UNKNOWN
        assert source.connectivity_revision == 1
        assert source.last_checked_at is None
