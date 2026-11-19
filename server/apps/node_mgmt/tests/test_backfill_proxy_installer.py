from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.management import call_command, CommandError

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv
from apps.node_mgmt.services.cloudregion import RegionService


USER = NodeConstants.NATS_INSTALLER_USERNAME_KEY
PASSWORD = NodeConstants.NATS_INSTALLER_PASSWORD_KEY
SENTINEL = "fixture-installer-secret"


@pytest.fixture
def regions():
    default = CloudRegion.objects.create(pk=1, name="default")
    region = CloudRegion.objects.create(pk=2, name="old-region", proxy_address="proxy.example")
    other = CloudRegion.objects.create(pk=3, name="other-region", proxy_address="other.example")
    SidecarEnv.objects.create(cloud_region=default, key=USER, value="installer", type="str")
    SidecarEnv.objects.create(cloud_region=default, key=PASSWORD, value=AESCryptor().encode(SENTINEL), type="secret")
    return region, other


@pytest.mark.django_db
def test_backfill_enables_existing_region_package_generation(regions, monkeypatch, tmp_path):
    region, other = regions
    output = StringIO()
    rollback_file = tmp_path / "proxy-region-2.record"
    for key, value in {
        "WEBHOOK_SERVER_URL": "http://webhookd",
        "DEFAULT_ZONE_VAR_NODE_SERVER_URL": "https://hub.example",
        "DEFAULT_ZONE_VAR_NATS_ADMIN_USERNAME": "admin",
        "DEFAULT_ZONE_VAR_NATS_ADMIN_PASSWORD": "fixture-admin",
        "PROXY_NATS_LEAF_URL": "tls://hub.example:7422",
        "PROXY_NATS_LEAF_USERNAME": "proxy-leaf",
        "PROXY_NATS_LEAF_PASSWORD": "fixture-leaf",
        "PROXY_NATS_SOURCE_DOMAIN": "bklite",
    }.items():
        monkeypatch.setenv(key, value)
    for key, value in (("NATS_USERNAME", "monitor"), ("NATS_PASSWORD", "fixture-monitor")):
        SidecarEnv.objects.create(cloud_region=region, key=key, value=value)
    SidecarEnv.objects.create(cloud_region=region, key=USER, value="", type="str")
    call_command("backfill_proxy_installer", region_id=region.pk, stdout=output)
    assert SidecarEnv.objects.get(cloud_region=region, key=USER).value == ""
    assert not SidecarEnv.objects.filter(cloud_region=region, key=PASSWORD).exists()
    call_command("backfill_proxy_installer", region_id=region.pk, apply=True, rollback_file=rollback_file, stdout=output)
    password = SidecarEnv.objects.get(cloud_region=region, key=PASSWORD)
    assert password.type == "secret" and password.value != SENTINEL
    assert rollback_file.stat().st_mode & 0o777 == 0o600
    assert SENTINEL not in rollback_file.read_text()
    call_command("backfill_proxy_installer", region_id=region.pk, apply=True, rollback_file=rollback_file, stdout=output)
    assert SidecarEnv.objects.get(pk=password.pk).value == password.value
    assert not SidecarEnv.objects.filter(cloud_region=other, key__in=[USER, PASSWORD]).exists()
    assert SENTINEL not in output.getvalue()
    response = SimpleNamespace(status_code=200, json=lambda: {"status": "success", "proxy_package_version": 2, "install_script": "fixture"})
    with patch("apps.node_mgmt.services.cloudregion.requests.post", return_value=response) as post:
        assert RegionService.get_deploy_script({"cloud_region_id": region.pk}) == "fixture"
    assert post.call_args.kwargs["json"]["nats_installer_password"] == SENTINEL

    call_command("backfill_proxy_installer", region_id=region.pk, rollback_file=rollback_file, restore=True, stdout=output)
    assert SidecarEnv.objects.filter(pk=password.pk).exists()
    for _ in range(2):
        call_command(
            "backfill_proxy_installer", region_id=region.pk, rollback_file=rollback_file, restore=True, apply=True, stdout=output,
        )
    assert SidecarEnv.objects.get(cloud_region=region, key=USER).value == ""
    assert not SidecarEnv.objects.filter(pk=password.pk).exists()
    assert not SidecarEnv.objects.filter(cloud_region=other, key__in=[USER, PASSWORD]).exists()
    assert SENTINEL not in output.getvalue()


@pytest.mark.django_db
def test_backfill_does_not_replace_partial_or_complete_custom_account(regions):
    region, _ = regions
    SidecarEnv.objects.create(cloud_region=region, key=USER, value="custom-installer", type="str")
    with pytest.raises(CommandError, match="配置不完整"):
        call_command("backfill_proxy_installer", region_id=region.pk, apply=True)
    assert not SidecarEnv.objects.filter(cloud_region=region, key=PASSWORD).exists()
    password = AESCryptor().encode("fixture-custom")
    SidecarEnv.objects.create(cloud_region=region, key=PASSWORD, value=password, type="secret")
    call_command("backfill_proxy_installer", region_id=region.pk, apply=True)
    assert dict(SidecarEnv.objects.filter(cloud_region=region).values_list("key", "value")) == {
        USER: "custom-installer", PASSWORD: password,
    }


@pytest.mark.django_db
def test_restore_refuses_other_region_or_modified_account(regions, tmp_path):
    region, other = regions
    path = tmp_path / "region.record"
    call_command("backfill_proxy_installer", region_id=region.pk, apply=True, rollback_file=path)
    with pytest.raises(CommandError, match="区域不匹配"):
        call_command("backfill_proxy_installer", region_id=other.pk, restore=True, apply=True, rollback_file=path)
    SidecarEnv.objects.filter(cloud_region=region, key=USER).update(value="replacement")
    with pytest.raises(CommandError, match="补齐后已变化"):
        call_command("backfill_proxy_installer", region_id=region.pk, restore=True, apply=True, rollback_file=path)
    assert SidecarEnv.objects.get(cloud_region=region, key=USER).value == "replacement"
    assert SidecarEnv.objects.filter(cloud_region=region, key=PASSWORD).exists()


@pytest.mark.django_db
def test_backfill_requires_a_new_rollback_file_before_committing(regions, tmp_path):
    region, _ = regions
    with pytest.raises(CommandError, match="--rollback-file"):
        call_command("backfill_proxy_installer", region_id=region.pk, apply=True)

    path = tmp_path / "existing.record"
    path.write_text("keep")
    with pytest.raises(CommandError, match="无法保存回退记录"):
        call_command("backfill_proxy_installer", region_id=region.pk, apply=True, rollback_file=path)
    assert path.read_text() == "keep"
    assert not SidecarEnv.objects.filter(cloud_region=region, key__in=[USER, PASSWORD]).exists()
