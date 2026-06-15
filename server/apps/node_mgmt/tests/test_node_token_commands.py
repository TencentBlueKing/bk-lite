from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.node_mgmt.models import CloudRegion, Node
from apps.node_mgmt.models.sidecar import SidecarApiToken
from apps.node_mgmt.utils.token_auth import decode_token


@pytest.mark.django_db
def test_reset_node_token_overwrites_existing_token_and_keeps_payload_fields(monkeypatch):
    node_id = "node-reset-token"
    SidecarApiToken.objects.create(node_id=node_id, token="old-token")
    cache_sets = []
    monkeypatch.setattr("apps.node_mgmt.utils.token_auth.cache.set", lambda key, value: cache_sets.append((key, value)))

    out = StringIO()
    call_command(
        "reset_node_token",
        "--node-id",
        node_id,
        "--ip",
        "10.0.0.8",
        "--user",
        "operator",
        stdout=out,
    )

    token_obj = SidecarApiToken.objects.get(node_id=node_id)
    payload = decode_token(token_obj.token, node_id=node_id)

    assert token_obj.token != "old-token"
    assert cache_sets == [(f"node_token_{node_id}", token_obj.token)]
    assert payload == {"node_id": node_id, "ip": "10.0.0.8", "user": "operator"}
    assert node_id in out.getvalue()
    assert token_obj.token in out.getvalue()


@pytest.mark.django_db
def test_reset_node_token_uses_node_ip_when_ip_argument_is_omitted():
    cloud_region = CloudRegion.objects.create(
        name="token-reset-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-reset-token-ip",
        name="node-reset-token-ip",
        ip="10.0.0.9",
        operating_system="linux",
        collector_configuration_directory="/etc/fusion-collectors",
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )

    call_command("reset_node_token", "--node-id", node.id)

    token = SidecarApiToken.objects.get(node_id=node.id).token
    assert decode_token(token, node_id=node.id) == {"node_id": node.id, "ip": node.ip, "user": "system"}


@pytest.mark.django_db
def test_reset_node_token_creates_missing_token_record_for_unknown_node_with_empty_ip():
    node_id = "node-token-record-missing"

    out = StringIO()
    call_command("reset_node_token", "--node-id", node_id, "--user", "", stdout=out)

    token = SidecarApiToken.objects.get(node_id=node_id).token
    assert decode_token(token, node_id=node_id) == {"node_id": node_id, "ip": "", "user": "system"}
    assert node_id in out.getvalue()
    assert token in out.getvalue()


@pytest.mark.django_db
def test_reset_node_token_rejects_blank_node_id():
    with pytest.raises(CommandError, match="--node-id 不能为空"):
        call_command("reset_node_token", "--node-id", "   ")
