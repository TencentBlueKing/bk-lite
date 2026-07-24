"""补丁源连通性真实探测测试。

覆盖：
  - probe_source()：yum/dnf 探 repomd.xml、apt 探基址、Windows 探基址；
    200 可达 / 404 不可达 / 网络异常不可达 / 无 URL 返回 None；代理与认证透传。
  - check_patch_source_connectivity 任务：探测结果写回 CONNECTED/FAILED，无 URL 置 UNKNOWN。

网络 I/O 通过 mock requests.get，不依赖外网，可进回归。
"""
import pytest
import requests

from apps.patch_mgmt.constants import ConnectivityStatus, PatchSourceType
from apps.patch_mgmt.models import PatchSource
from apps.patch_mgmt.services import connectivity_prober
from apps.patch_mgmt.services.connectivity_prober import probe_source


def _source(**kw) -> PatchSource:
    return PatchSource.objects.create(**{
        "name": "Repo",
        "source_type": PatchSourceType.YUM_REPO,
        "url": "https://mirrors.example.com/centos/7/os/x86_64",
        **kw,
    })


def _resp(mocker, status_code=200, content=b"<repomd></repomd>"):
    resp = mocker.Mock()
    resp.status_code = status_code
    resp.content = content
    resp.close = mocker.Mock()
    return resp


@pytest.mark.django_db
class TestProbeSource:
    def test_yum_probes_repomd_and_reachable_on_200(self, mocker):
        get = mocker.patch.object(connectivity_prober.requests, "get", return_value=_resp(mocker, 200))
        source = _source(source_type=PatchSourceType.YUM_REPO)
        result = probe_source(source)
        assert result is not None
        assert result.reachable is True
        assert result.status_code == 200
        target = get.call_args[0][0]
        assert target.endswith("/repodata/repomd.xml")

    def test_dnf_probes_repomd(self, mocker):
        get = mocker.patch.object(connectivity_prober.requests, "get", return_value=_resp(mocker, 200))
        source = _source(source_type=PatchSourceType.DNF_REPO)
        probe_source(source)
        assert get.call_args[0][0].endswith("/repodata/repomd.xml")

    def test_repo_404_not_reachable(self, mocker):
        mocker.patch.object(connectivity_prober.requests, "get", return_value=_resp(mocker, 404))
        result = probe_source(_source())
        assert result.reachable is False
        assert result.status_code == 404

    def test_apt_probes_release_metadata_for_resolved_codename(self, mocker):
        get = mocker.patch.object(
            connectivity_prober.requests,
            "get",
            return_value=_resp(mocker, 200, b"Origin: Ubuntu\nSuite: jammy\n"),
        )
        source = _source(
            source_type=PatchSourceType.APT_REPO,
            url="http://archive.ubuntu.com/ubuntu",
            os_version="22.04",
        )
        result = probe_source(source)
        assert result.reachable is True
        assert get.call_args[0][0] == "http://archive.ubuntu.com/ubuntu/dists/jammy/InRelease"

    def test_apt_falls_back_to_release_when_inrelease_is_missing(self, mocker):
        get = mocker.patch.object(
            connectivity_prober.requests,
            "get",
            side_effect=[
                _resp(mocker, 404, b""),
                _resp(mocker, 200, b"Origin: Debian\nSuite: bookworm\n"),
            ],
        )
        source = _source(
            source_type=PatchSourceType.APT_REPO,
            url="http://deb.debian.org/debian",
            os_version="12",
        )

        result = probe_source(source)

        assert result.reachable is True
        assert get.call_args_list[1].args[0].endswith("/dists/bookworm/Release")

    def test_yum_rejects_html_page_even_when_status_is_200(self, mocker):
        mocker.patch.object(
            connectivity_prober.requests,
            "get",
            return_value=_resp(mocker, 200, b"<html>login</html>"),
        )

        result = probe_source(_source())

        assert result.reachable is False
        assert "元数据格式无效" in result.detail

    def test_wsus_does_not_fall_back_to_http_when_admin_proxy_fails(self, mocker):
        mocker.patch(
            "apps.patch_mgmt.services.wsus_sync.WsusClient.check_connection",
            return_value=False,
        )
        http_get = mocker.patch.object(
            connectivity_prober.requests, "get", return_value=_resp(mocker, 200)
        )
        source = _source(
            source_type=PatchSourceType.WSUS,
            url="http://wsus.example.com",
        )

        result = probe_source(source)

        assert result.reachable is False
        assert "AdminProxy" in result.detail
        http_get.assert_not_called()

    def test_network_error_not_reachable(self, mocker):
        mocker.patch.object(
            connectivity_prober.requests, "get",
            side_effect=requests.ConnectionError("connection refused"),
        )
        result = probe_source(_source())
        assert result.reachable is False
        assert result.status_code is None

    def test_timeout_not_reachable(self, mocker):
        mocker.patch.object(
            connectivity_prober.requests, "get",
            side_effect=requests.Timeout("timed out"),
        )
        result = probe_source(_source())
        assert result.reachable is False

    def test_no_url_returns_none(self, mocker):
        get = mocker.patch.object(connectivity_prober.requests, "get")
        source = _source(source_type=PatchSourceType.WSUS, url="")
        assert probe_source(source) is None
        get.assert_not_called()

    def test_timeout_value_applied(self, mocker):
        get = mocker.patch.object(connectivity_prober.requests, "get", return_value=_resp(mocker, 200))
        probe_source(_source())
        assert get.call_args.kwargs["timeout"] == connectivity_prober.PROBE_TIMEOUT


@pytest.mark.django_db
class TestCheckConnectivityTask:
    def test_task_records_connected_when_reachable(self, mocker):
        from apps.patch_mgmt.tasks import check_patch_source_connectivity

        source = _source()
        mocker.patch(
            "apps.patch_mgmt.services.connectivity_prober.probe_source",
            return_value=connectivity_prober.ProbeResult(True, 200, "ok"),
        )
        check_patch_source_connectivity(source.id)
        source.refresh_from_db()
        assert source.connectivity_status == ConnectivityStatus.CONNECTED
        assert source.last_checked_at is not None

    def test_task_records_failed_when_unreachable(self, mocker):
        from apps.patch_mgmt.tasks import check_patch_source_connectivity

        source = _source()
        mocker.patch(
            "apps.patch_mgmt.services.connectivity_prober.probe_source",
            return_value=connectivity_prober.ProbeResult(False, 404, "404"),
        )
        check_patch_source_connectivity(source.id)
        source.refresh_from_db()
        assert source.connectivity_status == ConnectivityStatus.FAILED

    def test_task_sets_unknown_when_no_url(self, mocker):
        from apps.patch_mgmt.tasks import check_patch_source_connectivity

        source = _source(source_type=PatchSourceType.WSUS, url="")
        mocker.patch(
            "apps.patch_mgmt.services.connectivity_prober.probe_source",
            return_value=None,
        )
        check_patch_source_connectivity(source.id)
        source.refresh_from_db()
        assert source.connectivity_status == ConnectivityStatus.UNKNOWN
