from types import SimpleNamespace
from unittest.mock import patch

import django
import pytest

django.setup()

from apps.cmdb.nats import nats as N  # noqa: E402

UUID_1 = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"

HOST_ITEM = {
    "instance_uuid": UUID_1,
    "model_id": "host",
    "file_path": "/etc/ssh/sshd_config",
    "contents": ["# v1\nPermitRootLogin no\n", "# v2\nPermitRootLogin no\nPort 2222\n"],
}


def _params(**overrides):
    payload = {
        "protocol_version": "2",
        "allowed_org_ids": [1],
        "items": [HOST_ITEM],
    }
    payload.update(overrides)
    return payload


def _host_entity(**overrides):
    entity = {"_id": 11, "inst_uuid": UUID_1, "model_id": "host", "organization": [1]}
    entity.update(overrides)
    return entity


@patch("apps.cmdb.nats.nats.time.sleep")
@patch("apps.cmdb.nats.nats.ConfigFileVersion")
@patch("apps.cmdb.nats.nats.ConfigFileService")
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_manual_config_files_writes_versions(mock_im, mock_svc, mock_model, mock_sleep):
    mock_im.query_entity_by_uuid.return_value = _host_entity()
    mock_model.objects.filter.return_value.exists.return_value = False
    mock_svc.create_manual_version.side_effect = [
        {"unchanged": False, "version_obj": SimpleNamespace(id=1, version="v1")},
        {"unchanged": False, "version_obj": SimpleNamespace(id=2, version="v2")},
    ]

    result = N.create_manual_config_files(_params())

    assert result["result"] is True
    assert result["created"] == 1
    assert result["versions"] == 2
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert mock_svc.create_manual_version.call_count == 2
    first_kwargs = mock_svc.create_manual_version.call_args_list[0].kwargs
    assert first_kwargs["instance_id"] == "11"
    assert first_kwargs["instance_uuid"] == UUID_1
    assert first_kwargs["model_id"] == "host"
    assert first_kwargs["file_path"] == "/etc/ssh/sshd_config"
    assert first_kwargs["content"].startswith("# v1")
    mock_sleep.assert_called_once()


@patch("apps.cmdb.nats.nats.ConfigFileVersion")
@patch("apps.cmdb.nats.nats.ConfigFileService")
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_manual_config_files_skips_existing_file(mock_im, mock_svc, mock_model):
    mock_im.query_entity_by_uuid.return_value = _host_entity()
    mock_model.objects.filter.return_value.exists.return_value = True

    result = N.create_manual_config_files(_params())

    assert result == {"result": True, "created": 0, "versions": 0, "skipped": 1, "failed": 0, "errors": []}
    mock_svc.create_manual_version.assert_not_called()


@patch("apps.cmdb.nats.nats.ConfigFileService")
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_manual_config_files_missing_auth_rejects(mock_im, mock_svc):
    with pytest.raises(ValueError, match="authorization scope"):
        N.create_manual_config_files({"protocol_version": "2", "items": [HOST_ITEM]})
    mock_im.query_entity_by_uuid.assert_not_called()
    mock_svc.create_manual_version.assert_not_called()


@patch("apps.cmdb.nats.nats.ConfigFileService")
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_manual_config_files_requires_protocol_version(mock_im, mock_svc):
    with pytest.raises(ValueError, match="unsupported CMDB identity protocol version"):
        N.create_manual_config_files({"allowed_org_ids": [1], "items": [HOST_ITEM]})
    mock_svc.create_manual_version.assert_not_called()


@patch("apps.cmdb.nats.nats.ConfigFileService")
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_manual_config_files_rejects_legacy_instance_id(mock_im, mock_svc):
    with pytest.raises(ValueError, match="legacy numeric locators"):
        N.create_manual_config_files(_params(instance_id=11))
    mock_svc.create_manual_version.assert_not_called()


@patch("apps.cmdb.nats.nats.ConfigFileVersion")
@patch("apps.cmdb.nats.nats.ConfigFileService")
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_manual_config_files_org_outside_scope_fails_item(mock_im, mock_svc, mock_model):
    mock_im.query_entity_by_uuid.return_value = _host_entity(organization=[9])
    mock_model.objects.filter.return_value.exists.return_value = False

    result = N.create_manual_config_files(_params())

    assert result["created"] == 0
    assert result["failed"] == 1
    assert "outside authorization scope" in result["errors"][0]["error"]
    mock_svc.create_manual_version.assert_not_called()


@patch("apps.cmdb.nats.nats.ConfigFileService")
@patch("apps.cmdb.nats.nats.InstanceManage")
def test_create_manual_config_files_rejects_oversized_batch(mock_im, mock_svc):
    items = [{**HOST_ITEM, "instance_uuid": f"{UUID_1[:-2]}{index:02d}"} for index in range(51)]
    with pytest.raises(ValueError, match="items exceeds max"):
        N.create_manual_config_files(_params(items=items))
    mock_svc.create_manual_version.assert_not_called()
