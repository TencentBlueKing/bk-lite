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
from apps.node_mgmt.models.cloud_region import CloudRegion, CloudRegionService
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
def test_init_env_vars_copies_default_and_replaces_addresses(
    django_capture_on_commit_callbacks,
):
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
    with patch(
        "apps.node_mgmt.services.cloudregion.invalidate_sidecar_env_cache"
    ) as inv, django_capture_on_commit_callbacks(execute=True):
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


HUB_NODE_SERVER_URL = "https://hub.example:8443"
HUB_NATS_SERVERS = "tls://hub.example:4222"


def _ensure_hub_env():
    """默认云区域保存平台中心地址；必须先于自定义区域创建，避免抢占 id=1。"""
    region, _ = CloudRegion.objects.update_or_create(
        id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        defaults={"name": "default", "proxy_address": "127.0.0.1"},
    )
    for key, value in (
        (NodeConstants.SERVER_URL_KEY, HUB_NODE_SERVER_URL),
        (NodeConstants.NATS_SERVERS_KEY, HUB_NATS_SERVERS),
    ):
        SidecarEnv.objects.update_or_create(
            cloud_region=region,
            key=key,
            defaults={"value": value, "type": "str", "is_pre": True},
        )
    return region


def _create_custom_region(**kwargs):
    kwargs.setdefault("id", CloudRegionConstants.DEFAULT_CLOUD_REGION_ID + 1)
    return CloudRegion.objects.create(**kwargs)


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
    _ensure_hub_env()
    region = _create_custom_region(name="cr-deploy-ok", proxy_address="6.6.6.6")
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
    webhook_payload = post_mock.call_args.kwargs["json"]
    assert webhook_payload["server_url"] == HUB_NODE_SERVER_URL
    assert webhook_payload["nats_url"] == HUB_NATS_SERVERS
    assert webhook_payload["apm_nats_username"] == f"apm_region_{region.id}"
    assert len(webhook_payload["apm_nats_password"]) == 32


@pytest.mark.django_db
def test_get_deploy_script_maps_admin_and_monitor_nats_accounts():
    """管理员槽位取 NATS_ADMIN_*（区域变量优先），监控槽位取区域 NATS_USERNAME/PASSWORD。"""
    _ensure_hub_env()
    region = _create_custom_region(name="cr-deploy-nats-map", proxy_address="6.6.6.8")
    _build_complete_env(region.id)
    SidecarEnv.objects.filter(cloud_region=region, key="NATS_USERNAME").update(value="monitor")
    SidecarEnv.objects.filter(
        cloud_region=region, key=NodeConstants.NATS_PASSWORD_KEY
    ).update(value="monitorpass")
    SidecarEnv.objects.create(
        cloud_region=region, key="NATS_ADMIN_USERNAME", value="region-admin", type="str"
    )
    SidecarEnv.objects.create(
        cloud_region=region, key=NodeConstants.NATS_ADMIN_PASSWORD_KEY, value="region-adminpass", type="str"
    )

    def fake_getenv(key, default=None):
        # 进程环境提供不同的值，验证区域变量优先。
        return {"NATS_ADMIN_USERNAME": "env-admin", "NATS_ADMIN_PASSWORD": "env-adminpass"}.get(key, default)

    response = MagicMock(status_code=200)
    response.json.return_value = {"install_script": "echo ok"}

    with patch("apps.node_mgmt.services.cloudregion.os.getenv", side_effect=fake_getenv), patch(
        "apps.node_mgmt.services.cloudregion.requests.post", return_value=response
    ) as post_mock, patch(
        "apps.node_mgmt.services.cloudregion.generate_node_token", return_value="tok"
    ):
        RegionService.get_deploy_script({"cloud_region_id": region.id})

    webhook_payload = post_mock.call_args.kwargs["json"]
    assert webhook_payload["nats_username"] == "region-admin"
    assert webhook_payload["nats_password"] == "region-adminpass"
    assert webhook_payload["nats_monitor_username"] == "monitor"
    assert webhook_payload["nats_monitor_password"] == "monitorpass"


@pytest.mark.django_db
def test_get_deploy_script_rejects_identical_admin_and_monitor_username():
    """管理员与采集账号同名会让区域 NATS 因 duplicate user 无法启动，必须拒绝。"""
    _ensure_hub_env()
    region = _create_custom_region(name="cr-deploy-nats-dup", proxy_address="6.6.6.9")
    _build_complete_env(region.id)  # NATS_USERNAME = "admin"

    def fake_getenv(key, default=None):
        return {"NATS_ADMIN_USERNAME": "admin", "NATS_ADMIN_PASSWORD": "p"}.get(key, default)

    with patch("apps.node_mgmt.services.cloudregion.os.getenv", side_effect=fake_getenv), patch(
        "apps.node_mgmt.services.cloudregion.requests.post"
    ) as post_mock, pytest.raises(BaseAppException, match="不能相同"):
        RegionService.get_deploy_script({"cloud_region_id": region.id})

    post_mock.assert_not_called()


@pytest.mark.django_db
def test_get_deploy_script_prefers_runtime_webhook_url():
    _ensure_hub_env()
    region = _create_custom_region(
        name="cr-deploy-runtime-webhook",
        proxy_address="6.6.6.7",
    )
    _build_complete_env(region.id)

    def fake_getenv(key, default=None):
        return {
            "WEBHOOK_SERVER_URL": "http://127.0.0.1:18080",
            "NATS_ADMIN_USERNAME": "u",
            "NATS_ADMIN_PASSWORD": "p",
        }.get(key, default)

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"install_script": "echo hello"}

    with patch(
        "apps.node_mgmt.services.cloudregion.os.getenv",
        side_effect=fake_getenv,
    ), patch(
        "apps.node_mgmt.services.cloudregion.requests.post",
        return_value=response,
    ) as post_mock, patch(
        "apps.node_mgmt.services.cloudregion.generate_node_token",
        return_value="tok",
    ):
        RegionService.get_deploy_script({"cloud_region_id": region.id})

    called_url = post_mock.call_args.args[0]
    assert called_url == "http://127.0.0.1:18080/infra/proxy"


@pytest.mark.django_db
def test_get_deploy_script_rejects_default_cloud_region():
    region, _ = CloudRegion.objects.update_or_create(
        id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        defaults={"name": "default", "proxy_address": "127.0.0.1"},
    )

    with pytest.raises(BaseAppException) as exc:
        RegionService.get_deploy_script({"cloud_region_id": region.id})

    assert "平台统一维护" in str(exc.value)


@pytest.mark.django_db
def test_get_deploy_script_uses_pending_address_without_mutating_current_config():
    _ensure_hub_env()
    region = _create_custom_region(
        name="cr-deploy-pending",
        proxy_address="old.proxy.local",
        pending_proxy_address="new.proxy.local",
    )
    _build_complete_env(region.id)
    SidecarEnv.objects.filter(
        cloud_region=region,
        key="NODE_SERVER_URL",
    ).update(value="https://old.proxy.local:443")
    SidecarEnv.objects.filter(
        cloud_region=region,
        key="NATS_SERVERS",
    ).update(value="nats://old.proxy.local:4222")

    def fake_getenv(key, default=None):
        return {"NATS_ADMIN_USERNAME": "u", "NATS_ADMIN_PASSWORD": "p"}.get(key, default)

    response = MagicMock(status_code=200)
    response.json.return_value = {"install_script": "echo pending"}

    with patch("apps.node_mgmt.services.cloudregion.os.getenv", side_effect=fake_getenv), patch(
        "apps.node_mgmt.services.cloudregion.requests.post", return_value=response
    ) as post_mock, patch(
        "apps.node_mgmt.services.cloudregion.generate_node_token", return_value="tok"
    ):
        RegionService.get_deploy_script({"cloud_region_id": region.id})

    webhook_payload = post_mock.call_args.kwargs["json"]
    assert webhook_payload["proxy_ip"] == "new.proxy.local"
    assert webhook_payload["server_url"] == HUB_NODE_SERVER_URL
    assert webhook_payload["nats_url"] == HUB_NATS_SERVERS
    region.refresh_from_db()
    assert region.proxy_address == "old.proxy.local"
    assert SidecarEnv.objects.get(cloud_region=region, key="NODE_SERVER_URL").value == "https://old.proxy.local:443"


@pytest.mark.django_db
def test_get_deploy_script_keeps_hub_upstreams_after_custom_region_address_rewrite(
    django_capture_on_commit_callbacks,
):
    """自定义区域 NODE_SERVER_URL/NATS_SERVERS 会改成代理地址给节点用；
    部署脚本里的 Traefik/NATS leaf 上游必须仍指向平台中心，否则代理会反代自己，
    节点安装控制器时 curl linux_bootstrap 就会收到 500。"""
    _ensure_hub_env()
    region = _create_custom_region(name="cr-edge", proxy_address="10.0.0.9")
    SidecarEnv.objects.create(
        cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        key="WEBHOOK_SERVER_URL",
        value="https://webhook.local",
        type="str",
        is_pre=True,
    )
    SidecarEnv.objects.create(
        cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        key="NATS_USERNAME",
        value="admin",
        type="str",
        is_pre=True,
    )
    SidecarEnv.objects.create(
        cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        key=NodeConstants.NATS_PASSWORD_KEY,
        value="natspass",
        type="str",
        is_pre=True,
    )
    with django_capture_on_commit_callbacks(execute=True):
        RegionService.init_env_vars(region.id)

    rewritten_server = SidecarEnv.objects.get(
        cloud_region=region, key=NodeConstants.SERVER_URL_KEY
    ).value
    rewritten_nats = SidecarEnv.objects.get(
        cloud_region=region, key=NodeConstants.NATS_SERVERS_KEY
    ).value
    assert rewritten_server == "https://10.0.0.9:8443"
    assert rewritten_nats == "tls://10.0.0.9:4222"

    def fake_getenv(key, default=None):
        return {"NATS_ADMIN_USERNAME": "u", "NATS_ADMIN_PASSWORD": "p"}.get(key, default)

    response = MagicMock(status_code=200)
    response.json.return_value = {"install_script": "echo ok"}

    with patch("apps.node_mgmt.services.cloudregion.os.getenv", side_effect=fake_getenv), patch(
        "apps.node_mgmt.services.cloudregion.requests.post", return_value=response
    ) as post_mock, patch(
        "apps.node_mgmt.services.cloudregion.generate_node_token", return_value="tok"
    ):
        RegionService.get_deploy_script({"cloud_region_id": region.id})

    webhook_payload = post_mock.call_args.kwargs["json"]
    assert webhook_payload["proxy_ip"] == "10.0.0.9"
    assert webhook_payload["server_url"] == HUB_NODE_SERVER_URL
    assert webhook_payload["nats_url"] == HUB_NATS_SERVERS
    assert webhook_payload["server_url"] != rewritten_server
    assert webhook_payload["nats_url"] != rewritten_nats


@pytest.mark.django_db
def test_pending_deploy_script_rejects_proxy_environment_drift():
    region = CloudRegion.objects.create(
        name="cr-pending-drift",
        proxy_address="old.proxy.local",
        pending_proxy_address="new.proxy.local",
    )
    _build_complete_env(region.id)
    SidecarEnv.objects.filter(
        cloud_region=region,
        key=NodeConstants.SERVER_URL_KEY,
    ).update(value="https://unexpected.proxy.local:443")
    SidecarEnv.objects.filter(
        cloud_region=region,
        key=NodeConstants.NATS_SERVERS_KEY,
    ).update(value="nats://unexpected.proxy.local:4222")

    with patch(
        "apps.node_mgmt.services.cloudregion.requests.post"
    ) as post_mock, pytest.raises(BaseAppException, match="环境变量"):
        RegionService.get_deploy_script({"cloud_region_id": region.id})

    post_mock.assert_not_called()


@pytest.mark.django_db
def test_stage_and_cancel_proxy_address_do_not_change_current_address():
    region = CloudRegion.objects.create(name="cr-stage", proxy_address="old.proxy.local")

    RegionService.stage_proxy_address(region.id, "new.proxy.local")
    region.refresh_from_db()
    assert region.proxy_address == "old.proxy.local"
    assert region.pending_proxy_address == "new.proxy.local"
    assert region.pending_proxy_address_created_at is not None

    RegionService.cancel_pending_proxy_address(region.id)
    region.refresh_from_db()
    assert region.proxy_address == "old.proxy.local"
    assert region.pending_proxy_address is None
    assert region.pending_proxy_address_created_at is None


@pytest.mark.django_db
def test_stage_proxy_address_normalizes_ipv6_for_url_substitution():
    region = CloudRegion.objects.create(
        name="cr-stage-ipv6",
        proxy_address="old.proxy.local",
    )

    RegionService.stage_proxy_address(region.id, "2001:db8::8")

    region.refresh_from_db()
    assert region.pending_proxy_address == "[2001:db8::8]"


@pytest.mark.django_db
def test_activate_pending_proxy_address_requires_confirmation_and_healthy_services():
    region = CloudRegion.objects.create(
        name="cr-activate-guard",
        proxy_address="old.proxy.local",
        pending_proxy_address="new.proxy.local",
    )
    for service_name in CloudRegionServiceConstants.SERVICES:
        CloudRegionService.objects.create(
            cloud_region=region,
            name=service_name,
            status=CloudRegionServiceConstants.N_ERROR,
            deployed_status=CloudRegionServiceConstants.DEPLOYED,
        )

    with pytest.raises(BaseAppException, match="确认"):
        RegionService.activate_pending_proxy_address(region.id, confirmed=False)
    unhealthy_checks = {
        service_name: lambda _: (
            CloudRegionServiceConstants.N_ERROR,
            "unreachable",
        )
        for service_name in CloudRegionServiceConstants.SERVICES
    }
    with patch.dict(
        "apps.node_mgmt.tasks.services.cloud_service_check_health.SERVICES_FUNC",
        unhealthy_checks,
        clear=True,
    ), pytest.raises(BaseAppException, match="健康检查"):
        RegionService.activate_pending_proxy_address(region.id, confirmed=True)

    region.refresh_from_db()
    assert region.proxy_address == "old.proxy.local"
    assert region.pending_proxy_address == "new.proxy.local"


@pytest.mark.django_db
def test_activate_rechecks_live_health_instead_of_trusting_stored_status():
    region = CloudRegion.objects.create(
        name="cr-live-health",
        proxy_address="old.proxy.local",
        pending_proxy_address="new.proxy.local",
    )
    for service_name in CloudRegionServiceConstants.SERVICES:
        CloudRegionService.objects.create(
            cloud_region=region,
            name=service_name,
            status=CloudRegionServiceConstants.N_ERROR,
            deployed_status=CloudRegionServiceConstants.NOT_DEPLOYED_STATUS,
        )
    SidecarEnv.objects.create(
        cloud_region=region,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://old.proxy.local:443",
        type="str",
    )
    SidecarEnv.objects.create(
        cloud_region=region,
        key=NodeConstants.NATS_SERVERS_KEY,
        value="nats://old.proxy.local:4222",
        type="str",
    )
    live_checks = {
        CloudRegionServiceConstants.STARGAZER_SERVICE_NAME: lambda _: (
            CloudRegionServiceConstants.NORMAL,
            "ok",
        ),
        CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME: lambda _: (
            CloudRegionServiceConstants.N_ERROR,
            "unreachable",
        ),
    }

    with patch.dict(
        "apps.node_mgmt.tasks.services.cloud_service_check_health.SERVICES_FUNC",
        live_checks,
        clear=True,
    ), pytest.raises(BaseAppException, match="健康检查"):
        RegionService.activate_pending_proxy_address(region.id, confirmed=True)

    region.refresh_from_db()
    assert region.proxy_address == "old.proxy.local"
    assert region.pending_proxy_address == "new.proxy.local"


@pytest.mark.django_db
def test_activate_rolls_back_when_proxy_related_environment_has_drifted():
    region = CloudRegion.objects.create(
        name="cr-env-drift",
        proxy_address="old.proxy.local",
        pending_proxy_address="new.proxy.local",
    )
    for service_name in CloudRegionServiceConstants.SERVICES:
        CloudRegionService.objects.create(
            cloud_region=region,
            name=service_name,
            status=CloudRegionServiceConstants.N_ERROR,
            deployed_status=CloudRegionServiceConstants.NOT_DEPLOYED_STATUS,
        )
    SidecarEnv.objects.create(
        cloud_region=region,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://unexpected.proxy.local:443",
        type="str",
    )
    SidecarEnv.objects.create(
        cloud_region=region,
        key=NodeConstants.NATS_SERVERS_KEY,
        value="nats://unexpected.proxy.local:4222",
        type="str",
    )
    healthy_checks = {
        service_name: lambda _: (CloudRegionServiceConstants.NORMAL, "ok")
        for service_name in CloudRegionServiceConstants.SERVICES
    }

    with patch.dict(
        "apps.node_mgmt.tasks.services.cloud_service_check_health.SERVICES_FUNC",
        healthy_checks,
        clear=True,
    ), pytest.raises(BaseAppException, match="环境变量"):
        RegionService.activate_pending_proxy_address(region.id, confirmed=True)

    region.refresh_from_db()
    assert region.proxy_address == "old.proxy.local"
    assert region.pending_proxy_address == "new.proxy.local"
    assert (
        SidecarEnv.objects.get(
            cloud_region=region,
            key=NodeConstants.SERVER_URL_KEY,
        ).value
        == "https://unexpected.proxy.local:443"
    )


@pytest.mark.django_db
def test_activate_pending_proxy_address_updates_current_address_and_env_vars(
    django_capture_on_commit_callbacks,
):
    region = CloudRegion.objects.create(
        name="cr-activate",
        proxy_address="old.proxy.local",
        pending_proxy_address="new.proxy.local",
    )
    SidecarEnv.objects.create(
        cloud_region=region,
        key="NODE_SERVER_URL",
        value="https://old.proxy.local:443",
        type="str",
    )
    SidecarEnv.objects.create(
        cloud_region=region,
        key="NATS_SERVERS",
        value="nats://old.proxy.local:4222",
        type="str",
    )
    for service_name in CloudRegionServiceConstants.SERVICES:
        CloudRegionService.objects.create(
            cloud_region=region,
            name=service_name,
            status=CloudRegionServiceConstants.N_ERROR,
            deployed_status=CloudRegionServiceConstants.NOT_DEPLOYED_STATUS,
        )

    healthy_checks = {
        service_name: lambda _: (CloudRegionServiceConstants.NORMAL, "ok")
        for service_name in CloudRegionServiceConstants.SERVICES
    }
    with patch.object(
        RegionService,
        "_get_default_proxy_address",
        return_value="default.local",
    ), patch.dict(
        "apps.node_mgmt.tasks.services.cloud_service_check_health.SERVICES_FUNC",
        healthy_checks,
        clear=True,
    ), patch(
        "apps.node_mgmt.services.cloudregion.invalidate_sidecar_env_cache"
    ) as invalidate_cache, django_capture_on_commit_callbacks(execute=True):
        RegionService.activate_pending_proxy_address(region.id, confirmed=True)

    region.refresh_from_db()
    invalidate_cache.assert_called_once_with([region.id])
    assert region.proxy_address == "new.proxy.local"
    assert region.pending_proxy_address is None
    assert not region.cloudregionservice_set.exclude(
        status=CloudRegionServiceConstants.NORMAL,
        deployed_status=CloudRegionServiceConstants.DEPLOYED,
    ).exists()
    assert SidecarEnv.objects.get(cloud_region=region, key="NODE_SERVER_URL").value == "https://new.proxy.local:443"
    assert SidecarEnv.objects.get(cloud_region=region, key="NATS_SERVERS").value == "nats://new.proxy.local:4222"


@pytest.mark.django_db
def test_get_deploy_script_webhook_non_200_raises():
    _ensure_hub_env()
    region = _create_custom_region(name="cr-deploy-500", proxy_address="6.6.6.6")
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
    _ensure_hub_env()
    region = _create_custom_region(name="cr-deploy-timeout", proxy_address="6.6.6.6")
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
    _ensure_hub_env()
    region = _create_custom_region(name="cr-deploy-bodyerr", proxy_address="6.6.6.6")
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
