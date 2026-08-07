"""Linux yum/dnf repo 元数据同步测试(mock 网络,不依赖外网)。

覆盖:
  - fetch_advisories():解析 repomd → updateinfo,提取 id/类型/严重级别/CVE/包
  - 无 updateinfo / 非 yum 源 → 返回空
  - sync_linux_repo():建 Patch + LinuxPatchDetail、严重级别映射、team 继承、幂等
  - sync view action:返回计数;非 Linux 源 400
"""
import gzip

import pytest

from apps.patch_mgmt.constants import (
    OSType,
    PackageManagerType,
    PatchSeverity,
    PatchSourceType,
    PatchType,
)
from apps.patch_mgmt.models import LinuxPatchDetail, Patch, PatchSource
from apps.patch_mgmt.services import connectivity_prober  # noqa: F401 (确保 services 包可导入)
from apps.patch_mgmt.services import linux_repo_sync
from apps.patch_mgmt.services.linux_repo_sync import (
    ParsedAdvisory,
    ParsedPackage,
    RepoSyncError,
    fetch_advisories,
)
from apps.patch_mgmt.services.source_sync_service import (
    MAX_LINUX_PACKAGE_NAME_LENGTH,
    MAX_LINUX_PACKAGE_VERSION_LENGTH,
    MAX_LINUX_PACKAGES_PER_ADVISORY,
    SourceSyncError,
    SourceSyncService,
)

REPOMD = """<?xml version="1.0" encoding="UTF-8"?>
<repomd xmlns="http://linux.duke.edu/metadata/repo">
  <data type="primary"><location href="repodata/primary.xml.gz"/></data>
  <data type="updateinfo"><location href="repodata/updateinfo.xml.gz"/></data>
</repomd>"""

REPOMD_NO_UPDATEINFO = """<?xml version="1.0" encoding="UTF-8"?>
<repomd xmlns="http://linux.duke.edu/metadata/repo">
  <data type="primary"><location href="repodata/primary.xml.gz"/></data>
</repomd>"""

UPDATEINFO = """<?xml version="1.0"?>
<updates>
  <update from="x" status="final" type="security" version="2">
    <id>RHSA-2024:0001</id>
    <title>Important: openssl security update</title>
    <severity>Important</severity>
    <issued date="2024-01-01 00:00:00"/>
    <references>
      <reference href="h" id="CVE-2024-0001" type="cve" title="CVE-2024-0001"/>
      <reference href="h" id="CVE-2024-0002" type="cve" title="CVE-2024-0002"/>
    </references>
    <pkglist>
      <collection short="s">
        <package name="openssl" version="1.1.1k" release="7.el8" arch="x86_64"/>
        <package name="openssl-libs" version="1.1.1k" release="7.el8" arch="x86_64"/>
        <package name="openssl-libs" version="1.1.1k" release="7.el8" arch="x86_64"/>
        <package name="" version="1.1.1k" release="7.el8" arch="x86_64"/>
      </collection>
    </pkglist>
  </update>
  <update type="bugfix" version="1">
    <id>RHBA-2024:0002</id>
    <title>bash bugfix</title>
    <pkglist><collection><package name="bash" version="5.0" release="1.el8" arch="x86_64"/></collection></pkglist>
  </update>
</updates>"""


def _make_get(mocker, repomd=REPOMD, updateinfo=UPDATEINFO):
    def fake_get(url, **kwargs):
        resp = mocker.Mock()
        resp.raise_for_status = mocker.Mock()
        if url.endswith("repomd.xml"):
            resp.content = repomd.encode()
        elif "updateinfo" in url:
            resp.content = gzip.compress(updateinfo.encode())
        else:
            resp.content = b""
        return resp
    return mocker.patch.object(linux_repo_sync.requests, "get", side_effect=fake_get)


def _source(**kw) -> PatchSource:
    return PatchSource.objects.create(**{
        "name": "centos7",
        "source_type": PatchSourceType.YUM_REPO,
        "url": "https://mirror.example.com/centos/7/os/x86_64",
        "distro_name": "centos",
        "os_version": ">=7",
        "team": [1],
        **kw,
    })


@pytest.mark.django_db
class TestFetchAdvisories:
    def test_parses_two_advisories(self, mocker):
        _make_get(mocker)
        advs = fetch_advisories(_source())
        assert len(advs) == 2
        sec = advs[0]
        assert sec.advisory_id == "RHSA-2024:0001"
        assert sec.adv_type == "security"
        assert sec.severity == "Important"
        assert sec.cve_list == ["CVE-2024-0001", "CVE-2024-0002"]
        assert sec.packages[0].name == "openssl"
        assert sec.packages[0].version == "1.1.1k-7.el8"
        assert sec.packages[0].arch == "x86_64"
        assert [package.name for package in sec.packages] == [
            "openssl",
            "openssl-libs",
            "openssl-libs",
            "",
        ]

    def test_no_updateinfo_returns_empty(self, mocker):
        _make_get(mocker, repomd=REPOMD_NO_UPDATEINFO)
        assert fetch_advisories(_source()) == []

    def test_yum_source_fetch_uses_configured_proxy(self, mocker):
        get = _make_get(mocker)
        source = _source(proxy_host="proxy.example.com", proxy_port=8080)

        fetch_advisories(source)

        assert get.call_count == 2
        assert all(
            call.kwargs["proxies"]
            == {
                "http": "http://proxy.example.com:8080",
                "https": "http://proxy.example.com:8080",
            }
            for call in get.call_args_list
        )

    def test_x86_source_filters_i686_and_drops_advisories_without_matching_packages(
        self,
        mocker,
    ):
        updateinfo = """<?xml version="1.0"?>
<updates>
  <update type="security">
    <id>MIXED-1</id><title>mixed</title>
    <pkglist><collection>
      <package name="lib64" version="1" release="1" arch="x86_64"/>
      <package name="common" version="1" release="1" arch="noarch"/>
      <package name="lib32" version="1" release="1" arch="i686"/>
    </collection></pkglist>
  </update>
  <update type="security">
    <id>I686-ONLY</id><title>32 bit only</title>
    <pkglist><collection>
      <package name="lib32" version="1" release="1" arch="i686"/>
    </collection></pkglist>
  </update>
</updates>"""
        _make_get(mocker, updateinfo=updateinfo)

        advisories = fetch_advisories(_source(arch="x86_64"))

        assert [advisory.advisory_id for advisory in advisories] == ["MIXED-1"]
        assert [package.name for package in advisories[0].packages] == [
            "lib64",
            "common",
        ]
        assert {package.arch for package in advisories[0].packages} == {"x86_64"}

    def test_arm_source_keeps_aarch64_and_noarch_packages_as_canonical_arm64(
        self,
        mocker,
    ):
        updateinfo = """<?xml version="1.0"?>
<updates>
  <update type="security">
    <id>ARM-1</id><title>arm update</title>
    <pkglist><collection>
      <package name="arm" version="1" release="1" arch="aarch64"/>
      <package name="common" version="1" release="1" arch="noarch"/>
      <package name="intel" version="1" release="1" arch="x86_64"/>
    </collection></pkglist>
  </update>
</updates>"""
        _make_get(mocker, updateinfo=updateinfo)

        advisories = fetch_advisories(_source(arch="arm64"))

        assert [package.name for package in advisories[0].packages] == [
            "arm",
            "common",
        ]
        assert {package.arch for package in advisories[0].packages} == {"arm64"}

    def test_apt_source_fetches_packages_gz(self, mocker):
        """apt 源走 Packages.gz，不走 USN API。"""
        from apps.patch_mgmt.services import apt_sync

        packages_gz_content = """Package: openssl
Version: 3.0.2-0ubuntu1.10
Architecture: amd64
Depends: libc6 (>= 2.38), libssl3
Conflicts: old-openssl
Breaks: broken-pkg
Replaces: old-openssl
Description: SSL library

"""
        resp = mocker.Mock()
        resp.raise_for_status = mocker.Mock()
        resp.content = gzip.compress(packages_gz_content.encode())
        get = mocker.patch.object(apt_sync.requests, "get", return_value=resp)

        advs = fetch_advisories(
            _source(
                source_type=PatchSourceType.APT_REPO,
                url="https://mirrors.aliyun.com/ubuntu/",
                os_version="22.04",
                distro_name="Ubuntu",
                arch="x86_64",
            )
        )
        assert len(advs) == 1
        assert get.call_args.args[0].endswith("/binary-amd64/Packages.gz")
        assert advs[0].packages[0].name == "openssl"
        assert advs[0].packages[0].version == "3.0.2-0ubuntu1.10"
        assert advs[0].packages[0].arch == "x86_64"
        assert advs[0].severity == ""
        assert advs[0].install_deps.get("depends") == "libc6 (>= 2.38), libssl3"
        assert advs[0].install_deps.get("conflicts") == "old-openssl"
        assert advs[0].install_deps.get("breaks") == "broken-pkg"
        assert advs[0].install_deps.get("replaces") == "old-openssl"

    def test_missing_url_raises(self, mocker):
        _make_get(mocker)
        with pytest.raises(RepoSyncError):
            fetch_advisories(_source(url=""))


@pytest.mark.django_db
@pytest.mark.integration
class TestSyncLinuxRepo:
    @pytest.mark.parametrize(
        ("source_type", "expected_repo_type"),
        [
            (PatchSourceType.YUM_REPO, PackageManagerType.YUM),
            (PatchSourceType.DNF_REPO, PackageManagerType.DNF),
            (PatchSourceType.APT_REPO, PackageManagerType.APT),
        ],
    )
    def test_ingest_selected_creates_detail_for_each_linux_source(
        self,
        mocker,
        source_type,
        expected_repo_type,
    ):
        advisory = ParsedAdvisory(
            advisory_id=f"ADV-{expected_repo_type}",
            title=f"{expected_repo_type} security update",
            adv_type="security",
            severity="Important",
            packages=[
                ParsedPackage("kernel", "1.0", "x86_64"),
                ParsedPackage("kernel-tools", "1.0", "x86_64"),
            ],
        )
        mocker.patch(
            "apps.patch_mgmt.services.linux_repo_sync.fetch_advisories",
            return_value=[advisory],
        )
        source = _source(
            source_type=source_type,
            name=f"{expected_repo_type}-source",
        )

        result = SourceSyncService.ingest_selected(source, [advisory.advisory_id])

        assert result == {"created": 1, "updated": 0, "skipped": 0, "total": 1}
        detail = LinuxPatchDetail.objects.get(patch__title=advisory.advisory_id)
        assert detail.repo_type == expected_repo_type
        assert detail.packages == [
            {"name": "kernel", "version": "1.0", "arch": "x86_64"},
            {"name": "kernel-tools", "version": "1.0", "arch": "x86_64"},
        ]

    def test_ingest_selected_adds_current_team_idempotently_for_builtin_source(
        self, mocker
    ):
        advisory = ParsedAdvisory(
            advisory_id="ADV-GLOBAL-1",
            title="Global security update",
            adv_type="security",
            severity="Important",
            packages=[ParsedPackage("kernel", "1.0", "x86_64")],
        )
        mocker.patch(
            "apps.patch_mgmt.services.linux_repo_sync.fetch_advisories",
            return_value=[advisory],
        )
        source = _source(
            source_type=PatchSourceType.DNF_REPO,
            name="builtin-global",
            team=[],
            is_builtin=True,
            builtin_key="test-global-source",
        )

        first = SourceSyncService.ingest_selected(
            source, [advisory.advisory_id], team_id=1
        )
        second = SourceSyncService.ingest_selected(
            source, [advisory.advisory_id], team_id=1
        )

        patch = Patch.objects.get(title=advisory.advisory_id)
        assert first["created"] == 1
        assert second["updated"] == 1
        assert patch.team == [1]

    def test_builtin_source_ingest_rejects_missing_current_team(self, mocker):
        mocker.patch(
            "apps.patch_mgmt.services.linux_repo_sync.fetch_advisories",
            return_value=[],
        )
        source = _source(
            source_type=PatchSourceType.APT_REPO,
            name="builtin-without-team",
            team=[],
            is_builtin=True,
            builtin_key="test-builtin-without-team",
        )

        with pytest.raises(SourceSyncError, match="必须指定当前团队"):
            SourceSyncService.ingest_selected(source, ["ADV-INVISIBLE"])

        assert not Patch.objects.filter(title="ADV-INVISIBLE").exists()

    def test_creates_patches_and_details(self, mocker):
        _make_get(mocker)
        source = _source()
        result = SourceSyncService.sync_linux_repo(source)
        assert result == {"total": 2, "created": 2, "updated": 0}

        sec = Patch.objects.get(title="RHSA-2024:0001", os_type=OSType.LINUX)
        assert sec.os_type == OSType.LINUX
        assert sec.patch_type == PatchType.SECURITY
        assert sec.severity == PatchSeverity.IMPORTANT
        assert sec.cve_list == ["CVE-2024-0001", "CVE-2024-0002"]
        assert sec.team == [1]  # 继承补丁源团队
        assert source in sec.sources.all()

        detail = LinuxPatchDetail.objects.get(patch=sec)
        assert detail.pkg_name == "openssl"
        assert detail.pkg_version == "1.1.1k-7.el8"
        assert detail.distro_name == "centos"
        assert detail.repo_type == PackageManagerType.YUM
        assert detail.architectures == ["x86_64"]
        assert getattr(detail, "packages", []) == [
            {"name": "openssl", "version": "1.1.1k-7.el8", "arch": "x86_64"},
            {"name": "openssl-libs", "version": "1.1.1k-7.el8", "arch": "x86_64"},
        ]

    def test_preview_exposes_all_unique_packages_without_changing_legacy_name(
        self, mocker
    ):
        _make_get(mocker)
        source = _source()

        candidates = SourceSyncService.preview_sync_candidates(source)

        candidate = candidates[0]
        assert candidate["name"] == "openssl"
        assert candidate["version"] == "1.1.1k-7.el8"
        assert candidate["packages"] == [
            {"name": "openssl", "version": "1.1.1k-7.el8", "arch": "x86_64"},
            {"name": "openssl-libs", "version": "1.1.1k-7.el8", "arch": "x86_64"},
        ]

    def test_preview_and_ingest_accept_realistic_rpm_advisory_with_more_than_128_packages(
        self, mocker
    ):
        # Oracle/Rocky 9 当前真实 updateinfo 中的大公告可包含 205 个适用 RPM。
        unique_packages = [
            ParsedPackage(f"kernel-module-{index}", "1.0", "x86_64")
            for index in range(205)
        ]
        packages = unique_packages + [unique_packages[0]] * 600
        advisory = ParsedAdvisory(
            advisory_id="ELSA-2026:0129",
            title="Large kernel security advisory",
            adv_type="security",
            severity="Important",
            packages=packages,
        )
        mocker.patch(
            "apps.patch_mgmt.services.linux_repo_sync.fetch_advisories",
            return_value=[advisory],
        )

        source = _source(source_type=PatchSourceType.YUM_REPO)
        candidates = SourceSyncService.preview_sync_candidates(source)

        assert len(candidates) == 1
        assert candidates[0]["key"] == advisory.advisory_id
        assert candidates[0]["packages"] == [
            {"name": package.name, "version": package.version, "arch": "x86_64"}
            for package in unique_packages
        ]

        result = SourceSyncService.ingest_selected(source, [advisory.advisory_id])

        assert result == {"created": 1, "updated": 0, "skipped": 0, "total": 1}
        assert LinuxPatchDetail.objects.get(
            patch__title=advisory.advisory_id
        ).packages == candidates[0]["packages"]

    def test_sync_rolls_back_advisory_when_detail_persistence_fails(
        self, mocker
    ):
        _make_get(mocker)
        source = _source()
        mocker.patch.object(
            LinuxPatchDetail.objects,
            "update_or_create",
            side_effect=RuntimeError("detail write failed"),
        )

        with pytest.raises(RuntimeError, match="detail write failed"):
            SourceSyncService.sync_linux_repo(source)

        assert Patch.objects.filter(title="RHSA-2024:0001").exists() is False

    @pytest.mark.parametrize(
        ("packages", "error"),
        [
            ([ParsedPackage(f"pkg-{index}", "1.0", "x86_64") for index in range(MAX_LINUX_PACKAGES_PER_ADVISORY + 1)], "数量"),
            ([ParsedPackage("p" * (MAX_LINUX_PACKAGE_NAME_LENGTH + 1), "1.0", "x86_64")], "名称或版本过长"),
            ([ParsedPackage("kernel", "1" * (MAX_LINUX_PACKAGE_VERSION_LENGTH + 1), "x86_64")], "名称或版本过长"),
        ],
    )
    def test_sync_rejects_invalid_package_bounds_without_partial_persistence(self, mocker, packages, error):
        advisory = ParsedAdvisory(
            advisory_id="ADV-TOO-MANY",
            title="oversized advisory",
            adv_type="security",
            severity="Important",
            packages=packages,
        )
        mocker.patch("apps.patch_mgmt.services.linux_repo_sync.fetch_advisories", return_value=[advisory])

        with pytest.raises(SourceSyncError, match=error):
            SourceSyncService.sync_linux_repo(_source())

        assert not Patch.objects.filter(title=advisory.advisory_id).exists()

    def test_preview_and_selected_ingest_reject_oversized_version_without_persistence(self, mocker):
        advisory = ParsedAdvisory(
            advisory_id="ADV-TOO-MANY",
            title="oversized advisory",
            adv_type="security",
            severity="Important",
            packages=[ParsedPackage("kernel", "1" * (MAX_LINUX_PACKAGE_VERSION_LENGTH + 1), "x86_64")],
        )
        mocker.patch("apps.patch_mgmt.services.linux_repo_sync.fetch_advisories", return_value=[advisory])
        source = _source()

        with pytest.raises(SourceSyncError, match="名称或版本过长"):
            SourceSyncService.preview_sync_candidates(source)
        with pytest.raises(SourceSyncError, match="名称或版本过长"):
            SourceSyncService.ingest_selected(source, [advisory.advisory_id])

        assert not Patch.objects.filter(title=advisory.advisory_id).exists()

    def test_bugfix_maps_to_generic_moderate(self, mocker):
        _make_get(mocker)
        source = _source()
        SourceSyncService.sync_linux_repo(source)
        bug = Patch.objects.get(title="RHBA-2024:0002", os_type=OSType.LINUX)
        assert bug.patch_type == PatchType.GENERIC
        assert bug.severity == PatchSeverity.MODERATE

    def test_idempotent_on_resync(self, mocker):
        _make_get(mocker)
        source = _source()
        SourceSyncService.sync_linux_repo(source)
        result2 = SourceSyncService.sync_linux_repo(source)
        assert result2 == {"total": 2, "created": 0, "updated": 2}
        assert Patch.objects.filter(sources=source).count() == 2
        detail = LinuxPatchDetail.objects.get(patch__title="RHSA-2024:0001")
        assert len(getattr(detail, "packages", [])) == 2

    def test_non_linux_source_raises(self, mocker):
        _make_get(mocker)
        with pytest.raises(SourceSyncError):
            SourceSyncService.sync_linux_repo(_source(source_type="unsupported_source"))


@pytest.mark.django_db
class TestSyncViewApi:
    def test_sync_action_returns_counts(self, su_client, mocker):
        _make_get(mocker)
        source = _source()
        resp = su_client.post(f"/api/v1/patch_mgmt/api/patch_source/{source.id}/sync/")
        assert resp.status_code == 200
        assert resp.data["created"] == 2

    def test_sync_action_rejects_unsupported_source(self, su_client, mocker):
        """未知源类型同步被拒绝。"""
        _make_get(mocker)
        source = _source(source_type="unsupported_source", url="https://unsupported.example.com")
        resp = su_client.post(f"/api/v1/patch_mgmt/api/patch_source/{source.id}/sync/")
        assert resp.status_code == 400

    def test_sync_action_wsus_returns_error_without_server(self, su_client, mocker):
        """WSUS 源同步在没有 WSUS 服务器时返回 400（可接受，不 500）。"""
        source = _source(source_type=PatchSourceType.WSUS, url="https://wsus.invalid:8531")
        resp = su_client.post(f"/api/v1/patch_mgmt/api/patch_source/{source.id}/sync/")
        assert resp.status_code == 400
        assert "error" in resp.data

    def test_sync_action_apt_succeeds(self, su_client, mocker):
        """apt 源同步通过 Packages.gz 成功建档。"""
        from apps.patch_mgmt.services import apt_sync

        packages_gz_content = """Package: test-pkg
Version: 1.0-1ubuntu0.1
Architecture: amd64
Depends: libc6 (>= 2.38)
Description: Test package

"""
        resp = mocker.Mock()
        resp.raise_for_status = mocker.Mock()
        resp.content = gzip.compress(packages_gz_content.encode())
        mocker.patch.object(apt_sync.requests, "get", return_value=resp)

        source = _source(
            source_type=PatchSourceType.APT_REPO,
            url="https://mirrors.aliyun.com/ubuntu/",
            os_version="22.04",
            distro_name="Ubuntu",
            arch="x86_64",
        )
        resp = su_client.post(f"/api/v1/patch_mgmt/api/patch_source/{source.id}/sync/")
        assert resp.status_code == 200
        assert resp.data["total"] == 1
        assert resp.data["created"] == 1
