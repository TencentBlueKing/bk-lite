"""Linux repo 同步 view 测试。

sync view 会 import apps.node_mgmt.models.Node；相关 pytest 包装器
需要据此把 node_mgmt 列入 INSTALL_APPS。node_mgmt.urls 会再拉起 monitor。
"""
import gzip

import pytest

from apps.monitor.models import MonitorPlugin  # noqa: F401  INSTALL_APPS 需含 monitor（node_mgmt.urls → collector_release）
from apps.node_mgmt.models import Node  # noqa: F401  列表 URL 加载依赖 node_mgmt
from apps.patch_mgmt.constants import PatchSourceType
from apps.patch_mgmt.tests.linux_repo_sync_fixtures import _make_get, _source


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
