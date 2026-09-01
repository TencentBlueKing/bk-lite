"""手动采集视图：校验剩余分支与动作成功/失败契约。"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.monitor.views import manual_collect as mc
from apps.monitor.views.manual_collect import ManualCollect

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


def _user():
    return UserFactory(domain="domain.com", is_superuser=True)


def _json(resp):
    return json.loads(resp.content)


# --------------------------------------------------------------------------
# 校验剩余分支
# --------------------------------------------------------------------------


def test_cloud_area_list_wraps_node_mgmt_result():
    user = _user()
    request = factory.get("/cloud_region_list")
    force_authenticate(request, user=user)
    with patch.object(mc, "NodeMgmt", return_value=SimpleNamespace(cloud_region_list=lambda: [{"id": 1}])):
        resp = ManualCollect.as_view({"get": "cloud_area_list"})(request)
    body = _json(resp)
    assert resp.status_code == 200
    assert body["result"] is True
    assert body["data"] == [{"id": 1}]


def test_create_manual_instance_checks_orgs_and_returns_data():
    user = _user()
    request = factory.post(
        "/create_manual_instance",
        {"organizations": [1], "name": "x"},
        format="json",
    )
    force_authenticate(request, user=user)
    with (
        patch.object(mc, "_build_actor_context", return_value={"is_superuser": True, "current_team": 1}),
        patch.object(mc, "_ensure_target_organizations") as ensure_orgs,
        patch.object(
            mc.ManualCollectService,
            "create_manual_collect_instance",
            return_value={"id": "m1"},
        ) as created,
    ):
        resp = ManualCollect.as_view({"post": "create_manual_instance"})(request)
    ensure_orgs.assert_called_once()
    created.assert_called_once()
    body = _json(resp)
    assert resp.status_code == 200
    assert body["data"] == {"id": "m1"}


def test_flow_asset_binds_existing_instance_id():
    user = _user()
    payload = {
        "monitor_object_id": 3,
        "protocol": "netflow",
        "cloud_region_id": 2,
        "ip": "10.0.0.1",
        "name": "sw1",
        "instance_id": "inst-1",
        "organizations": [1],
    }
    request = factory.post("/flow_asset", payload, format="json")
    force_authenticate(request, user=user)
    with (
        patch.object(mc, "_build_actor_context", return_value={"is_superuser": True, "current_team": 1}),
        patch.object(mc.FlowOnboardingService, "lock_monitor_object"),
        patch.object(mc, "_validate_existing_flow_instance", return_value="inst-1") as validate,
        patch.object(mc, "_ensure_operate_instances") as ensure_ops,
        patch.object(mc, "_ensure_target_organizations"),
        patch.object(
            mc.FlowOnboardingService,
            "create_or_bind_asset",
            return_value={"instance_id": "inst-1"},
        ) as bind,
    ):
        resp = ManualCollect.as_view({"post": "flow_asset"})(request)
    validate.assert_called_once_with("inst-1")
    ensure_ops.assert_called()
    bind.assert_called_once()
    body = _json(resp)
    assert resp.status_code == 200
    assert body["data"]["instance_id"] == "inst-1"


def test_flow_asset_reuses_soft_deleted_asset():
    user = _user()
    payload = {
        "monitor_object_id": 3,
        "protocol": "sflow",
        "cloud_region_id": 2,
        "ip": "10.0.0.2",
        "name": "sw2",
    }
    request = factory.post("/flow_asset", payload, format="json")
    force_authenticate(request, user=user)
    existing = SimpleNamespace(id="reuse-1", is_deleted=True)
    with (
        patch.object(mc, "_build_actor_context", return_value={"is_superuser": True, "current_team": 1}),
        patch.object(mc.FlowOnboardingService, "lock_monitor_object"),
        patch.object(mc.FlowOnboardingService, "find_reusable_asset", return_value=existing),
        patch.object(mc, "_ensure_operate_instances") as ensure_ops,
        patch.object(mc, "_ensure_target_organizations"),
        patch.object(
            mc.FlowOnboardingService,
            "create_or_bind_asset",
            return_value={"instance_id": "reuse-1"},
        ) as bind,
    ):
        resp = ManualCollect.as_view({"post": "flow_asset"})(request)
    ensure_ops.assert_called()
    kwargs = bind.call_args.kwargs
    assert kwargs["instance_id"] == "reuse-1"
    assert kwargs["allow_deleted_instance_reuse"] is True
    assert _json(resp)["result"] is True


def test_update_flow_asset_and_access_guide_and_detect():
    user = _user()
    update_req = factory.post(
        "/flow_asset/update",
        {"instance_id": "inst-u", "name": "new"},
        format="json",
    )
    force_authenticate(update_req, user=user)
    with (
        patch.object(mc, "_build_actor_context", return_value={"is_superuser": True, "current_team": 1}),
        patch.object(mc, "_validate_existing_flow_instance", return_value="inst-u"),
        patch.object(mc, "_ensure_operate_instances"),
        patch.object(mc, "_ensure_target_organizations"),
        patch.object(mc.FlowOnboardingService, "update_asset", return_value={"ok": True}),
    ):
        resp = ManualCollect.as_view({"post": "update_flow_asset"})(update_req)
    assert resp.status_code == 200
    assert _json(resp)["data"] == {"ok": True}

    guide_req = factory.post(
        "/flow_access_guide",
        {"monitor_object_id": 1, "protocol": "netflow", "cloud_region_id": 2},
        format="json",
    )
    force_authenticate(guide_req, user=user)
    with patch.object(mc.FlowAccessGuideService, "build_document", return_value={"doc": "x"}) as built:
        resp = ManualCollect.as_view({"post": "flow_access_guide"})(guide_req)
    built.assert_called_once()
    assert _json(resp)["data"] == {"doc": "x"}

    detect_req = factory.post(
        "/flow_detect_status",
        {"instance_id": "inst-d", "monitor_object_id": 1, "protocol": "netflow", "time_window": "5m"},
        format="json",
    )
    force_authenticate(detect_req, user=user)
    with (
        patch.object(mc, "_build_actor_context", return_value={"is_superuser": True, "current_team": 1}),
        patch.object(mc, "_ensure_operate_instances") as ensure_ops,
        patch.object(mc.FlowOnboardingService, "detect_status", return_value={"status": "ok"}),
    ):
        resp = ManualCollect.as_view({"post": "flow_detect_status"})(detect_req)
    ensure_ops.assert_called()
    assert _json(resp)["data"] == {"status": "ok"}


def test_generate_install_command_and_check_collect_status():
    user = _user()
    cmd_req = factory.post(
        "/generate_install_command",
        {"instance_id": "inst-c", "cloud_region_id": 4},
        format="json",
    )
    force_authenticate(cmd_req, user=user)
    with (
        patch.object(mc, "_build_actor_context", return_value={"is_superuser": True, "current_team": 1}),
        patch.object(mc, "_ensure_operate_instances"),
        patch.object(mc.ManualCollectService, "generate_install_command", return_value={"cmd": "echo"}),
    ):
        resp = ManualCollect.as_view({"post": "generate_install_command"})(cmd_req)
    assert _json(resp)["data"] == {"cmd": "echo"}

    check_req = factory.post(
        "/check_collect_status",
        {"instance_id": "inst-c", "monitor_object_id": 9},
        format="json",
    )
    force_authenticate(check_req, user=user)
    with (
        patch.object(mc, "_build_actor_context", return_value={"is_superuser": True, "current_team": 1}),
        patch.object(mc, "_ensure_operate_instances"),
        patch.object(mc.ManualCollectService, "check_collect_status", return_value=True),
    ):
        resp = ManualCollect.as_view({"post": "check_collect_status"})(check_req)
    body = _json(resp)
    assert body["result"] is True
    assert body["data"] == {"success": True}


def test_flow_asset_unknown_field_raises():
    user = _user()
    request = factory.post("/flow_asset", {"foo": 1}, format="json")
    force_authenticate(request, user=user)
    with pytest.raises(ValidationAppException, match="Unknown request fields"):
        ManualCollect.as_view({"post": "flow_asset"})(request)
