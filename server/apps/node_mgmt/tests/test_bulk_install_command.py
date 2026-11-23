"""批量安装命令的对外行为：命令、受理、重复、重试和进度。"""

import json
import logging
import subprocess
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.utils import current_team_scope
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, PackageVersion, SidecarEnv
from apps.node_mgmt.models.installer import ControllerBulkAttempt
from apps.node_mgmt.models.sidecar import Node
from apps.node_mgmt.services.bulk_install import render_bulk_bootstrap_script
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.views import installer as installer_view
from apps.node_mgmt.views.sidecar import OpenSidecarViewSet
from apps.system_mgmt.models import Group

pytestmark = pytest.mark.django_db

NATS_SENTINEL = "nats-password-sentinel"
CREATED_LOG = "bulk install batch created batch_id=%s max_success_count=%s"
REVOKED_LOG = "bulk install batch revoked batch_id=%s"
DISABLED_LOG = "bulk install batch disabled batch_id=%s"


class _ScopedSystemMgmt:
    def get_authorized_groups_scoped(self, actor_context, include_children=False):
        return {"result": True, "data": [actor_context["current_team"]]}

    def get_assignable_groups(self, actor_context):
        return {"result": True, "data": [actor_context["current_team"]]}


@pytest.fixture(autouse=True)
def _teams(db):
    Group.objects.get_or_create(id=1, defaults={"name": "bulk-team", "parent_id": 0})
    Group.objects.get_or_create(id=2, defaults={"name": "other-team", "parent_id": 0})


@pytest.fixture(autouse=True)
def _locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "node-mgmt-bulk-install",
        }
    }
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def region(db):
    region = CloudRegion.objects.create(name="bulk-region")
    SidecarEnv.objects.create(
        cloud_region=region,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://node.example",
        type="text",
    )
    SidecarEnv.objects.create(
        cloud_region=region,
        key=NodeConstants.NATS_INSTALLER_PASSWORD_KEY,
        value=NATS_SENTINEL,
        type="secret",
    )
    return region


@pytest.fixture
def package(db):
    return PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="x86_64",
        object="Controller",
        version="1.2.3",
        name="controller",
    )


@pytest.fixture(autouse=True)
def _system_mgmt(monkeypatch):
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)


def _user(team="1"):
    return SimpleNamespace(
        username="alice",
        domain="domain.com",
        locale="zh",
        is_superuser=False,
        is_authenticated=True,
        group_list=[{"id": int(team), "name": "Team"}],
        permission={"node": {"cloud_region_node-Edit"}},
    )


def _auth(method, path, data=None, *, team="1"):
    factory = APIRequestFactory()
    request = getattr(factory, method)(path, data or {}, format="json")
    request.COOKIES["current_team"] = team
    request.COOKIES["include_children"] = "0"
    user = _user(team)
    force_authenticate(request, user=user)
    request.user = user
    return request


def _create_batch(region, package, **overrides):
    payload = {
        "cloud_region_id": region.id,
        "package_id": package.id,
        "max_success_count": 10,
        "expires_in_hours": 24,
        "push_targets": [],
    }
    payload.update(overrides)
    view = installer_view.InstallerViewSet.as_view({"post": "controller_bulk_install"})
    response = view(_auth("post", "/node_mgmt/api/installer/controller/bulk_install/", payload))
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def _enroll(token, ip="10.0.0.8", hostname="web-01", arch="x86_64"):
    view = OpenSidecarViewSet.as_view({"post": "bulk_enroll"})
    request = APIRequestFactory().post(
        "/node_mgmt/open_api/installer/bulk_enroll",
        {"token": token, "node_ip": ip, "hostname": hostname, "cpu_architecture": arch},
        format="json",
    )
    return view(request)


def _progress(batch_id, team="1"):
    view = installer_view.InstallerViewSet.as_view({"get": "controller_bulk_install_progress"})
    response = view(
        _auth("get", f"/node_mgmt/api/installer/controller/bulk_install/{batch_id}/", team=team),
        batch_id=batch_id,
    )
    return response


def _token(batch):
    import re

    match = re.search(r"token=([0-9a-f-]+)", batch["command"])
    assert match, batch["command"]
    return match.group(1)


def test_bulk_command_carries_node_ip_parameter_and_hides_nats_secret(region, package):
    batch = _create_batch(region, package)
    view = OpenSidecarViewSet.as_view({"get": "bulk_bootstrap"})
    script = view(APIRequestFactory().get("/node_mgmt/open_api/installer/bulk_bootstrap", {"token": _token(batch)}))

    assert "--node_ip" in batch["command"]
    assert _token(batch) in batch["command"]
    assert NATS_SENTINEL not in batch["command"]
    assert script.status_code == 200
    body = script.content.decode()
    assert "--node_ip" in body
    assert NATS_SENTINEL not in body


def test_enroll_creates_manual_node_from_hostname_and_node_ip(region, package):
    batch = _create_batch(region, package)
    response = _enroll(_token(batch), ip="10.0.0.8", hostname="web-01", arch="x86_64")

    assert response.status_code == 200, response.content
    node = Node.objects.get(ip="10.0.0.8", cloud_region=region)
    assert node.name == "web-01"
    assert node.install_method == ControllerConstants.MANUAL
    assert node.operating_system == "linux"
    assert node.cpu_architecture == "x86_64"
    progress = json.loads(_progress(batch["batch_id"]).content)["data"]
    assert progress["items"][0]["status"] == "installing"
    assert progress["accepted_count"] == 1


def test_existing_node_ip_is_duplicate_and_does_not_create_another(region, package):
    batch = _create_batch(region, package)
    assert _enroll(_token(batch)).status_code == 200
    before = Node.objects.filter(cloud_region=region, ip="10.0.0.8").count()

    duplicate = _enroll(_token(batch))

    assert duplicate.status_code == 400
    text = duplicate.content.decode()
    assert "重复" in text
    assert "10.0.0.8" in text
    assert "web-01" in text
    assert Node.objects.filter(cloud_region=region, ip="10.0.0.8").count() == before


def test_installing_placeholder_without_node_is_duplicate(region, package):
    batch = _create_batch(region, package)
    assert _enroll(_token(batch)).status_code == 200
    Node.objects.filter(cloud_region=region, ip="10.0.0.8").delete()

    duplicate = _enroll(_token(batch), hostname="other")

    assert duplicate.status_code == 400
    assert "重复" in duplicate.content.decode()
    assert "10.0.0.8" in duplicate.content.decode()
    assert Node.objects.filter(cloud_region=region, ip="10.0.0.8").count() == 0


def test_failed_install_releases_ip_for_another_attempt(region, package):
    batch = _create_batch(region, package)
    accepted = _enroll(_token(batch))
    node_id = accepted.content.decode().splitlines()[1]
    result = OpenSidecarViewSet.as_view({"post": "bulk_result"})(
        APIRequestFactory().post(
            "/node_mgmt/open_api/installer/bulk_result",
            {"token": _token(batch), "node_id": node_id, "outcome": "failed"},
            format="json",
        )
    )

    assert result.status_code == 200
    assert not Node.objects.filter(id=node_id).exists()
    retry = _enroll(_token(batch))
    assert retry.status_code == 200, retry.content
    assert Node.objects.filter(cloud_region=region, ip="10.0.0.8").count() == 1


def test_timed_out_install_can_be_accepted_again(region, package):
    batch = _create_batch(region, package)
    assert _enroll(_token(batch)).status_code == 200
    ControllerBulkAttempt.objects.filter(ip="10.0.0.8").update(
        created_at=timezone.now() - timedelta(seconds=InstallerConstants.CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS + 30)
    )

    retry = _enroll(_token(batch), hostname="web-02")

    assert retry.status_code == 200, retry.content
    assert Node.objects.get(cloud_region=region, ip="10.0.0.8").name == "web-02"
    statuses = [item["status"] for item in json.loads(_progress(batch["batch_id"]).content)["data"]["items"]]
    assert "timeout" in statuses
    assert "installing" in statuses


def test_full_batch_rejects_new_ip_but_existing_ip_stays_duplicate(region, package):
    batch = _create_batch(region, package, max_success_count=1)
    assert _enroll(_token(batch), ip="10.0.0.8", hostname="web-01").status_code == 200

    filled = _enroll(_token(batch), ip="10.0.0.9", hostname="web-02")
    duplicate = _enroll(_token(batch), ip="10.0.0.8", hostname="web-01")

    assert filled.status_code == 400
    assert "成功台数已满" in filled.content.decode()
    assert "重复" not in filled.content.decode()
    assert duplicate.status_code == 400
    assert "重复" in duplicate.content.decode()
    assert Node.objects.filter(cloud_region=region).count() == 1


def test_revoke_expired_and_failure_limit_reject_new_ips_and_keep_installed_nodes(region, package):
    batch = _create_batch(region, package, max_success_count=1)
    assert _enroll(_token(batch), ip="10.0.0.8", hostname="kept").status_code == 200
    revoke = installer_view.InstallerViewSet.as_view({"post": "controller_bulk_install_revoke"})(
        _auth("post", f"/node_mgmt/api/installer/controller/bulk_install/{batch['batch_id']}/revoke/"),
        batch_id=batch["batch_id"],
    )
    assert revoke.status_code == 200
    revoked = _enroll(_token(batch), ip="10.0.0.9", hostname="later")
    assert revoked.status_code == 400
    assert "已撤销" in revoked.content.decode()
    assert Node.objects.filter(name="kept").exists()

    expired = _create_batch(region, package)
    from apps.node_mgmt.models.installer import ControllerBulkBatch

    ControllerBulkBatch.objects.filter(id=expired["batch_id"]).update(expires_at=timezone.now() - timedelta(minutes=1))
    expired_response = _enroll(_token(expired), ip="10.0.1.1", hostname="late")
    assert expired_response.status_code == 400
    assert "已过期" in expired_response.content.decode()

    limited = _create_batch(region, package, max_success_count=1)
    for index in range(InstallerConstants.BULK_FAILURE_MULTIPLIER):
        failed = _enroll(_token(limited), ip=f"10.9.0.{index}", hostname="")
        assert failed.status_code == 400
        assert "读不到主机名" in failed.content.decode()
    disabled = _enroll(_token(limited), ip="10.9.0.20", hostname="after-limit")
    assert disabled.status_code == 400
    assert "已停用" in disabled.content.decode()
    assert Node.objects.filter(name="kept").exists()


def test_other_organization_cannot_read_or_revoke_the_batch(region, package):
    batch = _create_batch(region, package)
    progress = _progress(batch["batch_id"], team="2")
    revoke = installer_view.InstallerViewSet.as_view({"post": "controller_bulk_install_revoke"})(
        _auth("post", f"/node_mgmt/api/installer/controller/bulk_install/{batch['batch_id']}/revoke/", team="2"),
        batch_id=batch["batch_id"],
    )

    assert progress.status_code == 403
    assert revoke.status_code == 403
    assert _progress(batch["batch_id"]).status_code == 200


def test_missing_arm_package_fails_that_host_while_x86_can_enroll(region, package):
    batch = _create_batch(region, package)
    arm = _enroll(_token(batch), ip="10.2.0.1", hostname="arm-host", arch="arm64")
    x86 = _enroll(_token(batch), ip="10.2.0.2", hostname="x86-host", arch="x86_64")

    assert arm.status_code == 400
    assert "没有匹配的控制器版本" in arm.content.decode()
    assert x86.status_code == 200, x86.content
    assert not Node.objects.filter(ip="10.2.0.1").exists()
    assert Node.objects.filter(ip="10.2.0.2", cpu_architecture="x86_64").exists()


def _sidecar_heartbeat(region, node_id, ip):
    return SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "pushed-host",
            "node_details": {
                "ip": ip,
                "operating_system": "Linux",
                "cpu_architecture": "x86_64",
                "collector_configuration_directory": "/opt/fusion-collectors",
                "metrics": {},
                "status": {"status": 0},
                "tags": [
                    f"zone:{region.id}",
                    "group:1",
                    f"{ControllerConstants.INSTALL_METHOD_TAG}:{ControllerConstants.MANUAL}",
                    f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_HOST}",
                ],
                "log_file_list": [],
            },
        },
    )


def test_push_waits_for_the_first_sidecar_report_and_keeps_the_node(region, package, monkeypatch):
    calls = []

    def _push(*args, **kwargs):
        calls.append(kwargs.get("targets") or args)
        raise RuntimeError("cmdb down")

    monkeypatch.setattr("apps.node_mgmt.services.module_push.ModulePushService.push_node", _push)
    batch = _create_batch(region, package, push_targets=["cmdb"])
    accepted = _enroll(_token(batch), ip="10.3.0.1", hostname="pushed")

    assert accepted.status_code == 200, accepted.content
    node = Node.objects.get(ip="10.3.0.1")
    assert calls == []

    Sidecar.update_node_client(_sidecar_heartbeat(region, node.id, "10.3.0.1"), node.id)

    assert Node.objects.filter(id=node.id).exists()
    assert calls

    calls.clear()
    plain = _create_batch(region, package, push_targets=[])
    plain_accepted = _enroll(_token(plain), ip="10.3.0.2", hostname="plain")
    assert plain_accepted.status_code == 200
    plain_node = Node.objects.get(ip="10.3.0.2")
    Sidecar.update_node_client(_sidecar_heartbeat(region, plain_node.id, "10.3.0.2"), plain_node.id)
    assert calls == []
    assert Node.objects.filter(id=plain_node.id).exists()


def test_batch_lifecycle_logs_keep_template_and_omit_secrets(region, package, caplog):
    caplog.set_level(logging.DEBUG, logger="node")
    batch = _create_batch(region, package)
    token = _token(batch)
    created = [record for record in caplog.records if record.msg == CREATED_LOG]
    assert created[-1].args == (batch["batch_id"], 10)
    assert created[-1].getMessage() == f"bulk install batch created batch_id={batch['batch_id']} max_success_count=10"

    revoke = installer_view.InstallerViewSet.as_view({"post": "controller_bulk_install_revoke"})(
        _auth("post", f"/node_mgmt/api/installer/controller/bulk_install/{batch['batch_id']}/revoke/"),
        batch_id=batch["batch_id"],
    )
    assert revoke.status_code == 200
    revoked = [record for record in caplog.records if record.msg == REVOKED_LOG]
    assert revoked[-1].args == (batch["batch_id"],)
    assert revoked[-1].getMessage() == f"bulk install batch revoked batch_id={batch['batch_id']}"

    limited = _create_batch(region, package, max_success_count=1)
    for index in range(InstallerConstants.BULK_FAILURE_MULTIPLIER):
        failed = _enroll(_token(limited), ip=f"10.8.0.{index}", hostname="")
        assert failed.status_code == 400
    disabled = [record for record in caplog.records if record.msg == DISABLED_LOG]
    assert disabled[-1].args == (limited["batch_id"],)
    assert disabled[-1].getMessage() == f"bulk install batch disabled batch_id={limited['batch_id']}"
    assert token not in caplog.text
    assert NATS_SENTINEL not in caplog.text


def test_progress_lists_only_the_newest_bounded_attempts(region, package, monkeypatch):
    monkeypatch.setattr(InstallerConstants, "BULK_PROGRESS_ITEM_LIMIT", 1)
    batch = _create_batch(region, package)
    assert _enroll(_token(batch), ip="10.4.0.1", hostname="one").status_code == 200
    assert _enroll(_token(batch), ip="10.4.0.2", hostname="two").status_code == 200

    progress = json.loads(_progress(batch["batch_id"]).content)["data"]

    assert progress["accepted_count"] == 2
    assert len(progress["items"]) == 1
    assert progress["items"][0]["ip"] == "10.4.0.2"


def test_bootstrap_script_rejects_an_address_that_is_not_local(tmp_path):
    script = render_bulk_bootstrap_script(
        enroll_url="https://node.example/enroll",
        result_url="https://node.example/result",
        linux_bootstrap_url_prefix="https://node.example/bootstrap?token=",
        batch_token="batch-token",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl_log = tmp_path / "curl.log"
    (bin_dir / "ip").write_text("#!/bin/sh\necho '2: eth0 inet 10.1.1.1/24'\n", encoding="utf-8")
    (bin_dir / "curl").write_text(
        '#!/bin/sh\nprintf called >> "$CURL_LOG"\nexit 1\n',
        encoding="utf-8",
    )
    (bin_dir / "ip").chmod(0o755)
    (bin_dir / "curl").chmod(0o755)
    script_path = tmp_path / "bootstrap.sh"
    script_path.write_text(script, encoding="utf-8")

    result = subprocess.run(
        ["/bin/sh", str(script_path), "--node_ip", "10.0.0.8"],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CURL_LOG": str(curl_log)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "本机网卡上没有这个地址" in result.stderr
    assert not curl_log.exists()


def test_bootstrap_script_reports_failure_when_the_installer_download_fails(tmp_path):
    script = render_bulk_bootstrap_script(
        enroll_url="https://node.example/enroll",
        result_url="https://node.example/result",
        linux_bootstrap_url_prefix="https://node.example/bootstrap?token=",
        batch_token="batch-token",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl_log = tmp_path / "curl.log"
    (bin_dir / "ip").write_text("#!/bin/sh\necho '2: eth0 inet 10.0.0.8/24'\n", encoding="utf-8")
    (bin_dir / "hostname").write_text("#!/bin/sh\necho web-01\n", encoding="utf-8")
    (bin_dir / "curl").write_text(
        """#!/bin/sh
printf '%s\\n' "$*" >> "$CURL_LOG"
count=$(wc -l < "$CURL_LOG")
if [ "$count" -eq 1 ]; then
  prev=""
  for arg in "$@"; do
    if [ "$prev" = "-o" ]; then
      printf 'install-token\\nnode-id\\n' > "$arg"
    fi
    prev="$arg"
  done
  printf '200'
  exit 0
fi
if [ "$count" -eq 2 ]; then
  exit 1
fi
exit 0
""",
        encoding="utf-8",
    )
    for name in ("ip", "hostname", "curl"):
        (bin_dir / name).chmod(0o755)
    script_path = tmp_path / "bootstrap.sh"
    script_path.write_text(script, encoding="utf-8")

    result = subprocess.run(
        ["/bin/sh", str(script_path), "--node_ip", "10.0.0.8"],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CURL_LOG": str(curl_log)},
        text=True,
        capture_output=True,
        check=False,
    )

    logged = curl_log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "https://node.example/result" in logged
    assert "outcome=failed" in logged
