"""统一 OpenAPI 网关文件分发契约测试。"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.base.models import User, UserAPISecret
from apps.job_mgmt.models import DistributionFile, JobExecution, Target
from apps.node_mgmt.models import CloudRegion, Node, NodeOrganization
from apps.system_mgmt.models import Group
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

URL = "/openapi/v1/job-mgmt/file-distribute"


@pytest.fixture
def tenant():
    team = Group.objects.create(name="trusted-team")
    other_team = Group.objects.create(name="other-team")
    user = User.objects.create(username="file_app", domain="test.com")
    system_user = SystemUser.objects.create(
        username=user.username,
        domain=user.domain,
        group_list=[team.id],
    )
    token = UserAPISecret.generate_api_secret()
    UserAPISecret.objects.create(
        username=user.username,
        domain=user.domain,
        api_secret=UserAPISecret.hash_api_secret(token),
        team=team.id,
    )
    other_user = User.objects.create(username="other_file_app", domain="test.com")
    SystemUser.objects.create(username=other_user.username, domain=other_user.domain, group_list=[other_team.id])
    other_token = UserAPISecret.generate_api_secret()
    UserAPISecret.objects.create(
        username=other_user.username,
        domain=other_user.domain,
        api_secret=UserAPISecret.hash_api_secret(other_token),
        team=other_team.id,
    )
    file = DistributionFile.objects.create(
        original_name="trusted-package.tar.gz",
        file_key="job-files/trusted-package.tar.gz",
        expire_at=timezone.now() + timedelta(days=1),
        team=team.id,
    )
    target = Target.objects.create(name="web-01", ip="10.0.0.1", team=[team.id])
    return SimpleNamespace(
        team=team,
        other_team=other_team,
        user=user,
        system_user=system_user,
        token=token,
        other_token=other_token,
        file=file,
        target=target,
    )


def _auth(tenant):
    return {"HTTP_AUTHORIZATION": f"Bearer {tenant.token}"}


def _other_auth(tenant):
    return {"HTTP_AUTHORIZATION": f"Bearer {tenant.other_token}"}


def _body(tenant, **overrides):
    payload = {
        "name": "可信文件分发",
        "file_keys": [tenant.file.file_key],
        "target_source": "manual",
        "target_list": [{"target_id": tenant.target.id, "name": tenant.target.name, "ip": tenant.target.ip}],
        "target_path": "/tmp/patches/",
    }
    payload.update(overrides)
    return payload


def _assert_no_side_effects(mock_delay):
    assert not JobExecution.objects.filter(name="可信文件分发").exists()
    mock_delay.assert_not_called()


def test_api_tenant_can_distribute_own_file(tenant):
    client = APIClient()
    with patch("apps.job_mgmt.nats_api.DangerousChecker.check_path") as mock_check, patch(
        "apps.job_mgmt.nats_api.distribute_files_task.delay"
    ) as mock_delay, patch("apps.core.openapi.views.logger.info") as mock_audit:
        mock_check.return_value = MagicMock(can_execute=True, forbidden=[])
        mock_delay.return_value.id = "celery-1"
        response = client.post(URL, _body(tenant), format="json", **_auth(tenant))

    assert response.status_code == 200
    execution = JobExecution.objects.get(id=response.json()["data"]["task_id"])
    assert execution.team == [tenant.team.id]
    mock_check.assert_called_once_with("/tmp/patches/", [tenant.team.id])
    assert mock_audit.call_args.args[1] == tenant.user.username


def test_api_tenant_cannot_distribute_other_tenant_file(tenant):
    with patch("apps.job_mgmt.nats_api.distribute_files_task.delay") as mock_delay:
        response = APIClient().post(URL, _body(tenant), format="json", **_other_auth(tenant))

    assert response.status_code == 403
    assert response.json()["code"] == "TEAM_OUT_OF_SCOPE"
    _assert_no_side_effects(mock_delay)


def test_rejects_target_outside_api_secret_team(tenant):
    tenant.target.team = [tenant.other_team.id]
    tenant.target.save(update_fields=["team"])

    with patch("apps.job_mgmt.nats_api.distribute_files_task.delay") as mock_delay:
        response = APIClient().post(URL, _body(tenant), format="json", **_auth(tenant))

    assert response.status_code == 403
    assert response.json()["code"] == "TEAM_OUT_OF_SCOPE"
    _assert_no_side_effects(mock_delay)


def test_rejects_node_outside_api_secret_team_without_side_effects(tenant):
    region = CloudRegion.objects.create(name="file-distribute-region")
    node = Node.objects.create(
        id="node-outside-team",
        name="outside-node",
        ip="10.0.0.2",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=node, organization=tenant.other_team.id)
    payload = _body(
        tenant,
        target_source="node_mgmt",
        target_list=[{"node_id": node.id, "name": node.name, "ip": node.ip}],
    )

    with patch("apps.job_mgmt.nats_api.distribute_files_task.delay") as mock_delay:
        response = APIClient().post(URL, payload, format="json", **_auth(tenant))

    assert response.status_code == 403
    assert response.json()["code"] == "TEAM_OUT_OF_SCOPE"
    _assert_no_side_effects(mock_delay)


@pytest.mark.parametrize(
    "target_list",
    [
        [{"target_id": []}],
        [{"target_id": 1, "unknown": "value"}],
        [{"node_id": "node-in-manual-request"}],
    ],
)
def test_rejects_invalid_target_shape_without_side_effects(tenant, target_list):
    with patch("apps.job_mgmt.nats_api.distribute_files_task.delay") as mock_delay:
        response = APIClient().post(URL, _body(tenant, target_list=target_list), format="json", **_auth(tenant))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    _assert_no_side_effects(mock_delay)


def test_forged_team_is_rejected_without_side_effects(tenant):
    with patch("apps.job_mgmt.nats_api.distribute_files_task.delay") as mock_delay:
        response = APIClient().post(URL, _body(tenant, team=[999]), format="json", **_auth(tenant))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    _assert_no_side_effects(mock_delay)


@pytest.mark.parametrize("account_state", ["disabled", "inactive"])
def test_rejects_inactive_principal_without_side_effects(tenant, account_state):
    if account_state == "disabled":
        tenant.system_user.disabled = True
        tenant.system_user.save(update_fields=["disabled"])
    else:
        tenant.user.is_active = False
        tenant.user.save(update_fields=["is_active"])

    with patch("apps.job_mgmt.nats_api.distribute_files_task.delay") as mock_delay:
        response = APIClient().post(URL, _body(tenant), format="json", **_auth(tenant))

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID"
    _assert_no_side_effects(mock_delay)


def test_rejects_archived_api_secret_team_without_side_effects(tenant):
    tenant.team.is_delete = True
    tenant.team.save(update_fields=["is_delete"])

    with patch("apps.job_mgmt.nats_api.distribute_files_task.delay") as mock_delay:
        response = APIClient().post(URL, _body(tenant), format="json", **_auth(tenant))

    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"
    _assert_no_side_effects(mock_delay)


@pytest.mark.parametrize("payload", [[], "invalid"])
def test_rejects_non_object_json_without_side_effects(tenant, payload):
    with patch("apps.job_mgmt.nats_api.distribute_files_task.delay") as mock_delay:
        response = APIClient().post(URL, payload, format="json", **_auth(tenant))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    _assert_no_side_effects(mock_delay)


def test_rejects_uncontrolled_callback_without_side_effects(tenant):
    with patch("apps.job_mgmt.nats_api.distribute_files_task.delay") as mock_delay:
        response = APIClient().post(
            URL,
            _body(tenant, callback_url="http://internal/callback"),
            format="json",
            **_auth(tenant),
        )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    _assert_no_side_effects(mock_delay)
