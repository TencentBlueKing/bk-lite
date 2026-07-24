"""Linux yum/dnf repo 元数据同步测试(mock 网络,不依赖外网)。

覆盖:
  - fetch_advisories():解析 repomd → updateinfo,提取 id/类型/严重级别/CVE/包
  - 无 updateinfo / 非 yum 源 → 返回空
  - sync_linux_repo():建 Patch + LinuxPatchDetail、严重级别映射、team 继承、幂等
  - sync view action:返回计数;非 Linux 源 400
"""
import gzip

import pytest

from apps.patch_mgmt.constants import OSType, PatchSeverity, PatchSourceType, PatchType
from apps.patch_mgmt.models import LinuxPatchDetail, Patch, PatchSource
from apps.patch_mgmt.services import connectivity_prober  # noqa: F401 (确保 services 包可导入)
from apps.patch_mgmt.services import linux_repo_sync
from apps.patch_mgmt.services.linux_repo_sync import RepoSyncError, fetch_advisories
from apps.patch_mgmt.services.source_sync_service import SourceSyncError, SourceSyncService

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
      <collection short="s"><package name="openssl" version="1.1.1k" release="7.el8" arch="x86_64"/></collection>
    </pkglist>
  </update>
  <update type="bugfix" version="1">
    <id>RHBA-2024:0002</id>
    <title>bash bugfix</title>
    <pkglist><collection><package name="bash" version="5.0" release="1.el8" arch="x86_64"/></collection></pkglist>
  </update>
</updates>"""


def _make_get(mocker, repomd=REPOMD):
    def fake_get(url, **kwargs):
        resp = mocker.Mock()
        resp.raise_for_status = mocker.Mock()
        if url.endswith("repomd.xml"):
            resp.content = repomd.encode()
        elif "updateinfo" in url:
            resp.content = gzip.compress(UPDATEINFO.encode())
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

    def test_no_updateinfo_returns_empty(self, mocker):
        _make_get(mocker, repomd=REPOMD_NO_UPDATEINFO)
        assert fetch_advisories(_source()) == []

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
        mocker.patch.object(apt_sync.requests, "get", return_value=resp)

        advs = fetch_advisories(_source(source_type=PatchSourceType.APT_REPO, url="https://mirrors.aliyun.com/ubuntu/", os_version="22.04", distro_name="Ubuntu", arch="amd64"))
        assert len(advs) == 1
        assert advs[0].packages[0].name == "openssl"
        assert advs[0].packages[0].version == "3.0.2-0ubuntu1.10"
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
class TestSyncLinuxRepo:
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
        assert detail.repo_type == PatchSourceType.YUM_REPO
        assert detail.architectures == ["x86_64"]

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

        source = _source(source_type=PatchSourceType.APT_REPO, url="https://mirrors.aliyun.com/ubuntu/", os_version="22.04", distro_name="Ubuntu", arch="amd64")
        resp = su_client.post(f"/api/v1/patch_mgmt/api/patch_source/{source.id}/sync/")
        assert resp.status_code == 200
        assert resp.data["total"] == 1
        assert resp.data["created"] == 1
