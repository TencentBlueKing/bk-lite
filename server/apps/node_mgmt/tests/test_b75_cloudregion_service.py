"""RegionService 真实行为测试：环境变量解码/缓存、代理地址同步、初始化复制、部署脚本。

仅 mock 真实外部边界（requests.post webhook、AESCryptor 解密、cache）。
其余断言真实 DB 副作用与返回值。
"""
import pytest
from unittest.mock import MagicMock, patch

import requests

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.constants.database import CloudRegionConstants, EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import SidecarEnv
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.services.cloudregion import RegionService


# --------------------------------------------------------------------------- #
# get_region_service_instance_id
# --------------------------------------------------------------------------- #
def test_region_service_instance_id_nats_executor_returns_region_name():
    assert (
        RegionService.get_region_service_instance_id(
            "region-a", CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME
        )
        == "region-a"
    )


def test_region_service_instance_id_stargazer_appends_suffix():
    assert (
        RegionService.get_region_service_instance_id(
            "region-a", CloudRegionServiceConstants.STARGAZER_SERVICE_NAME
        )
        == "region-a_stargazer"
    )


def test_region_service_instance_id_unsupported_raises():
    with pytest.raises(BaseAppException) as exc:
        RegionService.get_region_service_instance_id("region-a", "unknown-service")
    assert "Unsupported cloud region service" in str(exc.value)


# --------------------------------------------------------------------------- #
# _decode_env_rows / get_cloud_region_envconfig
# --------------------------------------------------------------------------- #
def test_decode_env_rows_decodes_secret_and_filters_keys():
    rows = [
        {"key": "PLAIN", "value": "v1", "type": "str"},
        {"key": "SECRET", "value": "enc", "type": "secret"},
        {"key": "OTHER", "value": "v3", "type": "str"},
    ]
    with patch("apps.node_mgmt.services.cloudregion.AESCryptor") as aes_cls:
        aes_cls.return_value.decode.return_value = "decoded"
        result = RegionService._decode_env_rows(rows, keys=["PLAIN", "SECRET"])

    assert result == {"PLAIN": "v1", "SECRET": "decoded"}
    assert "OTHER" not in result


def test_decode_env_rows_secret_decode_failure_falls_back_to_raw():
    rows = [{"key": "SECRET", "value": "broken", "type": "secret"}]
    with patch("apps.node_mgmt.services.cloudregion.AESCryptor") as aes_cls:
        aes_cls.return_value.decode.side_effect = ValueError("bad")
        result = RegionService._decode_env_rows(rows)
    assert result == {"SECRET": "broken"}


@pytest.mark.django_db
def test_get_cloud_region_env_rows_reads_db_and_caches():
    region = CloudRegion.objects.create(name="cr-cache")
    SidecarEnv.objects.create(cloud_region=region, key="K1", value="V1", type="str")
    with patch("apps.node_mgmt.services.cloudregion.cache") as cache_mock:
        cache_mock.get.return_value = None
        rows = RegionService._get_cloud_region_env_rows(region.id)
        assert rows == [{"key": "K1", "value": "V1", "type": "str"}]
        cache_mock.set.assert_called_once()


@pytest.mark.django_db
def test_get_cloud_region_env_rows_returns_cached_value():
    with patch("apps.node_mgmt.services.cloudregion.cache") as cache_mock:
        cache_mock.get.return_value = [{"key": "CACHED", "value": "X", "type": "str"}]
        rows = RegionService._get_cloud_region_env_rows(999)
    assert rows == [{"key": "CACHED", "value": "X", "type": "str"}]


@pytest.mark.django_db
def test_get_cloud_region_envconfig_combines_rows_and_decode():
    region = CloudRegion.objects.create(name="cr-envcfg")
    SidecarEnv.objects.create(cloud_region=region, key="A", value="1", type="str")
    with patch("apps.node_mgmt.services.cloudregion.cache") as cache_mock:
        cache_mock.get.return_value = None
        result = RegionService.get_cloud_region_envconfig(region.id)
    assert result == {"A": "1"}


# --------------------------------------------------------------------------- #
# _extract_default_address / _replace_address
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://10.10.41.149:443", "10.10.41.149"),
        ("10.10.41.149:4223", "10.10.41.149"),
        ("https://api.example.com:443", "api.example.com"),
        ("https://[2001:db8::1]:443", "[2001:db8::1]"),
    ],
)
def test_extract_default_address(value, expected):
    assert RegionService._extract_default_address(value) == expected


def test_replace_address_basic_and_empty_guards():
    assert (
        RegionService._replace_address("https://10.0.0.1:443", "10.0.0.1", "host.local")
        == "https://host.local:443"
    )
    # 空地址直接返回原值
    assert RegionService._replace_address("v", "", "new") == "v"
    assert RegionService._replace_address("v", "old", "") == "v"


# --------------------------------------------------------------------------- #
# _sync_proxy_address_env_var
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_sync_proxy_address_env_var_creates_when_missing():
    region = CloudRegion.objects.create(name="cr-proxy-create", proxy_address="1.2.3.4")
    count = RegionService._sync_proxy_address_env_var(region.id, "1.2.3.4")
    assert count == 1
    env = SidecarEnv.objects.get(cloud_region=region, key=EnvVariableConstants.PROXY_ADDRESS_KEY)
    assert env.value == "1.2.3.4"
    assert env.is_pre is False


@pytest.mark.django_db
def test_sync_proxy_address_env_var_updates_changed_value():
    region = CloudRegion.objects.create(name="cr-proxy-update")
    SidecarEnv.objects.create(
        cloud_region=region,
        key=EnvVariableConstants.PROXY_ADDRESS_KEY,
        value="old",
        type="secret",
        is_pre=True,
        description="",
    )
    count = RegionService._sync_proxy_address_env_var(region.id, "new-addr")
    assert count == 1
    env = SidecarEnv.objects.get(cloud_region=region, key=EnvVariableConstants.PROXY_ADDRESS_KEY)
    assert env.value == "new-addr"
    assert env.type == EnvVariableConstants.TYPE_NORMAL
    assert env.is_pre is False
    assert env.description


@pytest.mark.django_db
def test_sync_proxy_address_env_var_no_change_returns_zero():
    region = CloudRegion.objects.create(name="cr-proxy-nochange")
    SidecarEnv.objects.create(
        cloud_region=region,
        key=EnvVariableConstants.PROXY_ADDRESS_KEY,
        value="same",
        type=EnvVariableConstants.TYPE_NORMAL,
        is_pre=False,
        description="云区域代理地址",
    )
    assert RegionService._sync_proxy_address_env_var(region.id, "same") == 0


# --------------------------------------------------------------------------- #
# _get_default_proxy_address
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_get_default_proxy_address_extracts_from_default_region():
    region = CloudRegion.objects.create(
        id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID, name="default-region-x"
    )
    SidecarEnv.objects.create(
        cloud_region=region,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://10.0.0.9:443",
        type="str",
        is_pre=True,
    )
    assert RegionService._get_default_proxy_address() == "10.0.0.9"


@pytest.mark.django_db
def test_get_default_proxy_address_returns_none_when_no_env():
    SidecarEnv.objects.filter(
        cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        key=NodeConstants.SERVER_URL_KEY,
    ).delete()
    assert RegionService._get_default_proxy_address() is None


# --------------------------------------------------------------------------- #
# _sync_proxy_address_replace_env_vars
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_sync_proxy_address_replace_env_vars_updates_matching_keys():
    region = CloudRegion.objects.create(name="cr-replace")
    SidecarEnv.objects.create(
        cloud_region=region,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://1.1.1.1:443",
        type="str",
    )
    updated = RegionService._sync_proxy_address_replace_env_vars(
        cloud_region_id=region.id,
        old_proxy_address="1.1.1.1",
        new_proxy_address="2.2.2.2",
        default_proxy_address="0.0.0.0",
    )
    assert updated == 1
    env = SidecarEnv.objects.get(cloud_region=region, key=NodeConstants.SERVER_URL_KEY)
    assert env.value == "https://2.2.2.2:443"


@pytest.mark.django_db
def test_sync_proxy_address_replace_env_vars_same_address_noop():
    region = CloudRegion.objects.create(name="cr-replace-same")
    updated = RegionService._sync_proxy_address_replace_env_vars(
        cloud_region_id=region.id,
        old_proxy_address="x",
        new_proxy_address="x",
        default_proxy_address="d",
    )
    assert updated == 0


@pytest.mark.django_db
def test_sync_proxy_address_replace_env_vars_no_default_returns_zero():
    region = CloudRegion.objects.create(name="cr-replace-nodefault")
    updated = RegionService._sync_proxy_address_replace_env_vars(
        cloud_region_id=region.id,
        old_proxy_address="",
        new_proxy_address="",
        default_proxy_address=None,
    )
    assert updated == 0


# --------------------------------------------------------------------------- #
# init_env_vars
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_init_env_vars_region_not_found_returns_zero():
    assert RegionService.init_env_vars(123456) == 0


@pytest.mark.django_db
def test_init_env_vars_copies_default_and_replaces_addresses():
    default_region = CloudRegion.objects.create(
        id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID, name="default-init"
    )
    SidecarEnv.objects.create(
        cloud_region=default_region,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://10.0.0.1:443",
        type="str",
        is_pre=True,
    )
    SidecarEnv.objects.create(
        cloud_region=default_region,
        key="PLAIN_VAR",
        value="plain",
        type="str",
        is_pre=True,
    )
    new_region = CloudRegion.objects.create(name="new-init", proxy_address="9.9.9.9")
    with patch("apps.node_mgmt.services.cloudregion.invalidate_sidecar_env_cache") as inv:
        created = RegionService.init_env_vars(new_region.id)
    assert created >= 2
    inv.assert_called_once()
    server_env = SidecarEnv.objects.get(cloud_region=new_region, key=NodeConstants.SERVER_URL_KEY)
    assert server_env.value == "https://9.9.9.9:443"
    assert server_env.is_pre is False


@pytest.mark.django_db
def test_init_env_vars_no_default_vars_only_syncs_proxy():
    SidecarEnv.objects.filter(
        cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID
    ).delete()
    new_region = CloudRegion.objects.create(name="new-init-empty", proxy_address="3.3.3.3")
    created = RegionService.init_env_vars(new_region.id)
    # 仅创建了 PROXY_ADDRESS 一条
    assert created == 1
    assert SidecarEnv.objects.filter(
        cloud_region=new_region, key=EnvVariableConstants.PROXY_ADDRESS_KEY
    ).exists()


# --------------------------------------------------------------------------- #
# update_env_vars_on_proxy_change
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_update_env_vars_on_proxy_change_delegates_to_sync():
    region = CloudRegion.objects.create(name="cr-update-proxy")
    with patch.object(RegionService, "sync_proxy_related_env_vars", return_value=5) as m:
        result = RegionService.update_env_vars_on_proxy_change(region.id, "old", "new")
    assert result == 5
    m.assert_called_once()


@pytest.mark.django_db
def test_update_env_vars_on_proxy_change_swallows_exception():
    with patch.object(
        RegionService, "sync_proxy_related_env_vars", side_effect=RuntimeError("boom")
    ):
        assert RegionService.update_env_vars_on_proxy_change(1, "a", "b") == 0


# --------------------------------------------------------------------------- #
# get_deploy_script
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_get_deploy_script_invalid_cloud_region_id_raises():
    with pytest.raises(BaseAppException) as exc:
        RegionService.get_deploy_script({"cloud_region_id": "not-int"})
    assert "Invalid cloud_region_id" in str(exc.value)


@pytest.mark.django_db
def test_get_deploy_script_region_not_found_raises():
    with pytest.raises(BaseAppException) as exc:
        RegionService.get_deploy_script({"cloud_region_id": 777777})
    assert "Cloud region not found" in str(exc.value)


def _build_complete_env(region_id):
    base = {
        "WEBHOOK_SERVER_URL": "https://webhook.local",
        "NODE_SERVER_URL": "https://node.local",
        "NATS_SERVERS": "nats://nats.local:4222",
        "NATS_USERNAME": "admin",
        NodeConstants.NATS_PASSWORD_KEY: "natspass",
    }
    for k, v in base.items():
        SidecarEnv.objects.create(cloud_region_id=region_id, key=k, value=v, type="str")


@pytest.mark.django_db
def test_get_deploy_script_missing_webhook_url_raises():
    region = CloudRegion.objects.create(name="cr-deploy-nowebhook", proxy_address="5.5.5.5")
    with patch("apps.node_mgmt.services.cloudregion.os.getenv", return_value=None):
        with pytest.raises(BaseAppException) as exc:
            RegionService.get_deploy_script({"cloud_region_id": region.id})
    assert "Webhook configuration missing" in str(exc.value)


@pytest.mark.django_db
def test_get_deploy_script_missing_required_vars_raises():
    region = CloudRegion.objects.create(name="cr-deploy-incomplete", proxy_address="5.5.5.5")
    SidecarEnv.objects.create(
        cloud_region=region, key="WEBHOOK_SERVER_URL", value="https://wh", type="str"
    )

    def fake_getenv(key, default=None):
        return {"NATS_ADMIN_USERNAME": "u", "NATS_ADMIN_PASSWORD": "p"}.get(key, default)

    with patch("apps.node_mgmt.services.cloudregion.os.getenv", side_effect=fake_getenv):
        with pytest.raises(BaseAppException) as exc:
            RegionService.get_deploy_script({"cloud_region_id": region.id})
    assert "environment configuration is incomplete" in str(exc.value)


@pytest.mark.django_db
def test_get_deploy_script_success_calls_webhook_and_returns_script():
    region = CloudRegion.objects.create(name="cr-deploy-ok", proxy_address="6.6.6.6")
    _build_complete_env(region.id)

    def fake_getenv(key, default=None):
        return {"NATS_ADMIN_USERNAME": "u", "NATS_ADMIN_PASSWORD": "p"}.get(key, default)

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"install_script": "echo hello"}

    with patch("apps.node_mgmt.services.cloudregion.os.getenv", side_effect=fake_getenv), patch(
        "apps.node_mgmt.services.cloudregion.requests.post", return_value=response
    ) as post_mock, patch(
        "apps.node_mgmt.services.cloudregion.generate_node_token", return_value="tok"
    ):
        script = RegionService.get_deploy_script({"cloud_region_id": region.id})

    assert script == "echo hello"
    called_url = post_mock.call_args.args[0]
    assert called_url == "https://webhook.local/infra/proxy"


@pytest.mark.django_db
def test_get_deploy_script_webhook_non_200_raises():
    region = CloudRegion.objects.create(name="cr-deploy-500", proxy_address="6.6.6.6")
    _build_complete_env(region.id)

    def fake_getenv(key, default=None):
        return {"NATS_ADMIN_USERNAME": "u", "NATS_ADMIN_PASSWORD": "p"}.get(key, default)

    response = MagicMock()
    response.status_code = 500
    response.text = "err"

    with patch("apps.node_mgmt.services.cloudregion.os.getenv", side_effect=fake_getenv), patch(
        "apps.node_mgmt.services.cloudregion.requests.post", return_value=response
    ), patch("apps.node_mgmt.services.cloudregion.generate_node_token", return_value="tok"):
        with pytest.raises(BaseAppException) as exc:
            RegionService.get_deploy_script({"cloud_region_id": region.id})
    assert "Failed to generate deploy script" in str(exc.value)


@pytest.mark.django_db
def test_get_deploy_script_webhook_timeout_raises():
    region = CloudRegion.objects.create(name="cr-deploy-timeout", proxy_address="6.6.6.6")
    _build_complete_env(region.id)

    def fake_getenv(key, default=None):
        return {"NATS_ADMIN_USERNAME": "u", "NATS_ADMIN_PASSWORD": "p"}.get(key, default)

    with patch("apps.node_mgmt.services.cloudregion.os.getenv", side_effect=fake_getenv), patch(
        "apps.node_mgmt.services.cloudregion.requests.post", side_effect=requests.Timeout()
    ), patch("apps.node_mgmt.services.cloudregion.generate_node_token", return_value="tok"):
        with pytest.raises(BaseAppException) as exc:
            RegionService.get_deploy_script({"cloud_region_id": region.id})
    assert "timeout" in str(exc.value).lower()


@pytest.mark.django_db
def test_get_deploy_script_webhook_error_status_in_body_raises():
    region = CloudRegion.objects.create(name="cr-deploy-bodyerr", proxy_address="6.6.6.6")
    _build_complete_env(region.id)

    def fake_getenv(key, default=None):
        return {"NATS_ADMIN_USERNAME": "u", "NATS_ADMIN_PASSWORD": "p"}.get(key, default)

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"status": "error", "message": "bad config"}

    with patch("apps.node_mgmt.services.cloudregion.os.getenv", side_effect=fake_getenv), patch(
        "apps.node_mgmt.services.cloudregion.requests.post", return_value=response
    ), patch("apps.node_mgmt.services.cloudregion.generate_node_token", return_value="tok"):
        with pytest.raises(BaseAppException) as exc:
            RegionService.get_deploy_script({"cloud_region_id": region.id})
    assert "bad config" in str(exc.value)
