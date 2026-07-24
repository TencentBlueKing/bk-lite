from datetime import datetime, timezone as dt_timezone

import pytest

from apps.patch_mgmt.constants import ConnectivityStatus, OSType, PatchSourceType
from apps.patch_mgmt.models import PatchSource
from apps.patch_mgmt.services import PatchSourceService


def _source(**overrides):
    values = {
        "name": "Ubuntu Repo",
        "source_type": PatchSourceType.APT_REPO,
        "distro_name": "ubuntu",
        "os_version": "22.04",
        "is_enabled": True,
    }
    values.update(overrides)
    return PatchSource.objects.create(**values)


@pytest.mark.django_db
class TestPatchSourceService:
    @pytest.mark.parametrize(
        ("initial", "operation", "expected"),
        [
            (False, PatchSourceService.enable, True),
            (True, PatchSourceService.enable, True),
            (True, PatchSourceService.disable, False),
            (False, PatchSourceService.disable, False),
        ],
    )
    def test_enable_and_disable_are_idempotent(self, initial, operation, expected):
        source = _source(is_enabled=initial)

        operation(source)

        source.refresh_from_db()
        assert source.is_enabled is expected

    def test_connectivity_update_persists_status_and_explicit_time(self):
        source = _source()
        checked_at = datetime(2026, 1, 1, 12, 0, tzinfo=dt_timezone.utc)

        PatchSourceService.update_connectivity(
            source,
            ConnectivityStatus.FAILED,
            checked_at=checked_at,
        )

        source.refresh_from_db()
        assert source.connectivity_status == ConnectivityStatus.FAILED
        assert source.last_checked_at == checked_at

    def test_invalid_connectivity_status_is_rejected(self):
        source = _source()

        with pytest.raises(ValueError, match="无效的连通性状态"):
            PatchSourceService.update_connectivity(source, "invalid")

    @pytest.mark.parametrize(
        "source",
        [
            PatchSource(name="WSUS", source_type=PatchSourceType.WSUS, url=""),
            PatchSource(
                name="APT",
                source_type=PatchSourceType.APT_REPO,
                distro_name="",
                os_version="22.04",
            ),
            PatchSource(
                name="YUM",
                source_type=PatchSourceType.YUM_REPO,
                distro_name="rocky",
                os_version="",
            ),
        ],
    )
    def test_incomplete_source_configuration_is_rejected(self, source):
        with pytest.raises(ValueError):
            PatchSourceService.validate_source_fields(source)

    def test_list_enabled_honors_enabled_and_os_type(self):
        windows = _source(
            name="WSUS",
            source_type=PatchSourceType.WSUS,
            url="http://wsus.example.com",
            distro_name="",
            os_version="",
        )
        _source(name="disabled", is_enabled=False)
        linux = _source(name="APT")

        assert list(PatchSourceService.list_enabled(OSType.WINDOWS)) == [windows]
        assert list(PatchSourceService.list_enabled(OSType.LINUX)) == [linux]
