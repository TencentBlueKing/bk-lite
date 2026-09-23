"""存量 Linux 公告空 packages 的有界运行期重同步。

升级前入库的 LinuxPatchDetail.packages=[] 没有只补这一批空快照的入口：
整库同步会拉全量，内置源禁止 sync，同步入库把已入库候选标为 added。
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.patch_mgmt.constants import OSType, PatchSourceType
from apps.patch_mgmt.models import LinuxPatchDetail, Patch, PatchSource
from apps.patch_mgmt.services.linux_repo_sync import (
    ParsedAdvisory,
    ParsedPackage,
    RepoSyncError,
)
from apps.patch_mgmt.services.source_sync_service import SourceSyncError, SourceSyncService

FILLED_PACKAGES = [
    {"name": "openssl", "version": "1.1.1k-7.el8", "arch": "x86_64"},
    {"name": "openssl-libs", "version": "1.1.1k-7.el8", "arch": "x86_64"},
]


def _advisory(advisory_id: str, packages=None) -> ParsedAdvisory:
    return ParsedAdvisory(
        advisory_id=advisory_id,
        title=f"{advisory_id} security update",
        adv_type="security",
        severity="Important",
        packages=packages
        or [
            ParsedPackage("openssl", "1.1.1k-7.el8", "x86_64"),
            ParsedPackage("openssl-libs", "1.1.1k-7.el8", "x86_64"),
        ],
    )


def _source(**kwargs) -> PatchSource:
    payload = {
        "name": "centos7",
        "source_type": PatchSourceType.YUM_REPO,
        "url": "https://mirror.example.com/centos/7/os/x86_64",
        "distro_name": "centos",
        "os_version": ">=7",
        "team": [1],
    }
    payload.update(kwargs)
    return PatchSource.objects.create(**payload)


def _empty_detail(source: PatchSource, title: str, *, pkg_name: str = "openssl") -> LinuxPatchDetail:
    patch = Patch.objects.create(title=title, os_type=OSType.LINUX, team=[1])
    patch.sources.add(source)
    return LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name=pkg_name,
        pkg_version="1.0",
        packages=[],
        distro_name="centos",
        os_version_range=">=7",
        architectures=["x86_64"],
        repo_type="yum",
    )


def _patch_fetch(mocker, advisories, *, side_effect=None):
    return mocker.patch(
        "apps.patch_mgmt.services.linux_repo_sync.fetch_advisories",
        return_value=advisories,
        side_effect=side_effect,
    )


def _assert_jsonable(result: dict) -> None:
    encoded = json.dumps(result, ensure_ascii=False)
    assert json.loads(encoded) == result


@pytest.mark.django_db
def test_existing_apis_cannot_bounded_fill_empty_packages(mocker):
    """已入库空 packages 不能靠现有整库同步或同步入库只补这一批。"""
    source = _source()
    detail = _empty_detail(source, "RHSA-LEGACY-1")
    extra = _advisory("RHSA-NEW-2", [ParsedPackage("bash", "5.0", "x86_64")])
    _patch_fetch(mocker, [_advisory("RHSA-LEGACY-1"), extra])

    preview = SourceSyncService.preview_sync_candidates(source)
    assert preview[0]["added"] is True
    assert preview[0]["key"] == "RHSA-LEGACY-1"
    detail.refresh_from_db()
    assert detail.packages == []

    result = SourceSyncService.sync_linux_repo(source)
    assert result["created"] >= 1
    assert Patch.objects.filter(title="RHSA-NEW-2").exists()

    builtin = _source(
        name="builtin-linux",
        is_builtin=True,
        builtin_key="test-empty-packages-builtin",
        team=[],
    )
    builtin_detail = _empty_detail(builtin, "RHSA-BUILTIN-1")
    _patch_fetch(mocker, [_advisory("RHSA-BUILTIN-1")])
    with pytest.raises(SourceSyncError, match="必须指定当前团队"):
        SourceSyncService.ingest_selected(builtin, ["RHSA-BUILTIN-1"])
    builtin_detail.refresh_from_db()
    assert builtin_detail.packages == []


@pytest.mark.django_db
def test_resync_fills_legacy_single_package_empty_list(mocker):
    source = _source()
    detail = _empty_detail(source, "RHSA-LEGACY-1")
    fetch = _patch_fetch(mocker, [_advisory("RHSA-LEGACY-1")])

    result = SourceSyncService.resync_empty_linux_packages(source_id=source.id, limit=10)

    _assert_jsonable(result)
    assert result["scanned"] == 1
    assert result["filled"] == 1
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert result["dry_run"] is False
    assert result["items"][0]["status"] == "filled"
    assert result["items"][0]["patch_id"] == detail.pk
    assert result["items"][0]["source_id"] == source.id
    detail.refresh_from_db()
    assert detail.packages == FILLED_PACKAGES
    assert detail.pkg_name == "openssl"
    assert fetch.call_count == 1


@pytest.mark.django_db
def test_resync_builtin_source_and_already_ingested_candidate(mocker):
    source = _source(
        name="builtin-linux",
        is_builtin=True,
        builtin_key="test-empty-packages-resync",
        team=[],
    )
    detail = _empty_detail(source, "RHSA-BUILTIN-1")
    _patch_fetch(mocker, [_advisory("RHSA-BUILTIN-1")])

    preview = SourceSyncService.preview_sync_candidates(source)
    assert preview[0]["added"] is True

    result = SourceSyncService.resync_empty_linux_packages(source_id=source.id)

    assert result["filled"] == 1
    detail.refresh_from_db()
    assert detail.packages == FILLED_PACKAGES


@pytest.mark.django_db
def test_resync_regular_source_without_source_id(mocker):
    source = _source(name="regular-linux")
    other = _source(name="other-linux")
    target = _empty_detail(source, "RHSA-REG-1")
    ignored = _empty_detail(other, "RHSA-OTHER-1")
    _patch_fetch(mocker, [_advisory("RHSA-REG-1"), _advisory("RHSA-OTHER-1")])

    result = SourceSyncService.resync_empty_linux_packages(source_id=source.id, limit=10)

    assert result["scanned"] == 1
    assert result["filled"] == 1
    target.refresh_from_db()
    ignored.refresh_from_db()
    assert target.packages == FILLED_PACKAGES
    assert ignored.packages == []


@pytest.mark.django_db
def test_resync_dry_run_does_not_write(mocker):
    source = _source()
    detail = _empty_detail(source, "RHSA-DRY-1")
    _patch_fetch(mocker, [_advisory("RHSA-DRY-1")])

    result = SourceSyncService.resync_empty_linux_packages(source_id=source.id, dry_run=True)

    assert result["dry_run"] is True
    assert result["filled"] == 1
    assert result["items"][0]["status"] == "filled"
    detail.refresh_from_db()
    assert detail.packages == []


@pytest.mark.django_db
def test_resync_is_idempotent_and_skips_nonempty_packages(mocker):
    source = _source()
    empty = _empty_detail(source, "RHSA-IDEM-1")
    filled_patch = Patch.objects.create(title="RHSA-IDEM-2", os_type=OSType.LINUX, team=[1])
    filled_patch.sources.add(source)
    LinuxPatchDetail.objects.create(
        patch=filled_patch,
        pkg_name="bash",
        pkg_version="5.0",
        packages=[{"name": "bash", "version": "5.0", "arch": "x86_64"}],
        distro_name="centos",
        os_version_range=">=7",
        architectures=["x86_64"],
        repo_type="yum",
    )
    _patch_fetch(
        mocker,
        [_advisory("RHSA-IDEM-1"), _advisory("RHSA-IDEM-2", [ParsedPackage("bash", "9.9", "x86_64")])],
    )

    first = SourceSyncService.resync_empty_linux_packages(source_id=source.id)
    second = SourceSyncService.resync_empty_linux_packages(source_id=source.id)

    assert first["filled"] == 1
    assert first["scanned"] == 1
    assert second["filled"] == 0
    assert second["scanned"] == 0
    empty.refresh_from_db()
    filled_patch.linux_detail.refresh_from_db()
    assert empty.packages == FILLED_PACKAGES
    assert filled_patch.linux_detail.packages == [{"name": "bash", "version": "5.0", "arch": "x86_64"}]


@pytest.mark.django_db
def test_resync_source_unavailable_fails_that_source_batch(mocker):
    source = _source()
    other = _source(name="healthy-linux")
    failed_detail = _empty_detail(source, "RHSA-DOWN-1")
    healthy = _empty_detail(other, "RHSA-OK-1")

    def fake_fetch(current_source):
        if current_source.pk == source.pk:
            raise RepoSyncError("mirror unavailable")
        return [_advisory("RHSA-OK-1")]

    _patch_fetch(mocker, None, side_effect=fake_fetch)

    result = SourceSyncService.resync_empty_linux_packages(limit=10)

    assert result["failed"] == 1
    assert result["filled"] == 1
    assert {item["status"] for item in result["items"] if item["patch_id"] == failed_detail.pk} == {"failed"}
    failed_detail.refresh_from_db()
    healthy.refresh_from_db()
    assert failed_detail.packages == []
    assert healthy.packages == FILLED_PACKAGES


@pytest.mark.django_db
def test_resync_partial_failure_retries_only_failed_items(mocker):
    source = _source()
    ok = _empty_detail(source, "RHSA-OK-1")
    bad = _empty_detail(source, "RHSA-BAD-1")
    oversized = [ParsedPackage("p" * 300, "1.0", "x86_64")]
    fetch = _patch_fetch(
        mocker,
        [_advisory("RHSA-OK-1"), _advisory("RHSA-BAD-1", oversized)],
    )

    first = SourceSyncService.resync_empty_linux_packages(source_id=source.id)
    assert first["filled"] == 1
    assert first["failed"] == 1
    assert fetch.call_count == 1
    ok.refresh_from_db()
    bad.refresh_from_db()
    assert ok.packages == FILLED_PACKAGES
    assert bad.packages == []

    fetch.return_value = [_advisory("RHSA-BAD-1")]
    second = SourceSyncService.resync_empty_linux_packages(source_id=source.id)
    assert second["scanned"] == 1
    assert second["filled"] == 1
    assert second["failed"] == 0
    bad.refresh_from_db()
    assert bad.packages == FILLED_PACKAGES


@pytest.mark.django_db
def test_resync_limit_and_after_id_bounds(mocker):
    source = _source()
    first = _empty_detail(source, "RHSA-LIMIT-1")
    second = _empty_detail(source, "RHSA-LIMIT-2")
    _patch_fetch(mocker, [_advisory("RHSA-LIMIT-1"), _advisory("RHSA-LIMIT-2")])

    with pytest.raises(SourceSyncError, match="1 到 1000"):
        SourceSyncService.resync_empty_linux_packages(limit=0)
    with pytest.raises(SourceSyncError, match="1 到 1000"):
        SourceSyncService.resync_empty_linux_packages(limit=1001)

    result = SourceSyncService.resync_empty_linux_packages(source_id=source.id, limit=1)
    assert result["scanned"] == 1
    assert result["filled"] == 1
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.packages == FILLED_PACKAGES
    assert second.packages == []

    next_batch = SourceSyncService.resync_empty_linux_packages(
        source_id=source.id,
        limit=1,
        after_id=first.pk,
    )
    assert next_batch["scanned"] == 1
    second.refresh_from_db()
    assert second.packages == FILLED_PACKAGES


@pytest.mark.django_db
def test_resync_groups_one_fetch_per_source(mocker):
    source = _source()
    _empty_detail(source, "RHSA-GROUP-1")
    _empty_detail(source, "RHSA-GROUP-2")
    fetch = _patch_fetch(mocker, [_advisory("RHSA-GROUP-1"), _advisory("RHSA-GROUP-2")])

    result = SourceSyncService.resync_empty_linux_packages(source_id=source.id, limit=10)

    assert result["filled"] == 2
    assert fetch.call_count == 1


@pytest.mark.django_db
def test_resync_command_defaults_to_dry_run_and_can_write(mocker):
    source = _source()
    detail = _empty_detail(source, "RHSA-CMD-1")
    _patch_fetch(mocker, [_advisory("RHSA-CMD-1")])

    dry_out = StringIO()
    call_command("resync_linux_patch_packages", stdout=dry_out)
    dry_result = json.loads(dry_out.getvalue())
    assert dry_result["dry_run"] is True
    detail.refresh_from_db()
    assert detail.packages == []

    write_out = StringIO()
    call_command(
        "resync_linux_patch_packages",
        dry_run=False,
        source_id=source.id,
        limit=10,
        stdout=write_out,
    )
    write_result = json.loads(write_out.getvalue())
    assert write_result["dry_run"] is False
    assert write_result["filled"] == 1
    detail.refresh_from_db()
    assert detail.packages == FILLED_PACKAGES


def test_resync_command_help_is_upgrade_guidance():
    help_text = (
        Path(__file__).resolve().parents[1] / "management/commands/resync_linux_patch_packages.py"
    ).read_text(encoding="utf-8")
    assert "空 packages" in help_text
    assert "升级" in help_text
    assert "dry-run" in help_text.lower() or "不写库" in help_text


def test_resync_command_is_not_wired_into_startup_or_migrations():
    server = Path(__file__).resolve().parents[3]
    texts = [
        (server / "apps/core/management/commands/batch_init.py").read_text(encoding="utf-8"),
        (server / "apps/patch_mgmt/apps.py").read_text(encoding="utf-8"),
    ]
    texts.extend(path.read_text(encoding="utf-8") for path in (server / "apps/patch_mgmt/migrations").glob("*.py"))
    for text in texts:
        assert "resync_linux_patch_packages" not in text
        assert "resync_empty_linux_packages" not in text
