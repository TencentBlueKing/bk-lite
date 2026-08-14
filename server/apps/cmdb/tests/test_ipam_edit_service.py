# -- coding: utf-8 --
"""IP 视图手工登记纯逻辑。"""
import pytest

from apps.cmdb.services.ipam_edit import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_NOOP,
    ACTION_UPDATE,
    IpamEditError,
    decide_manual_ip_action,
    find_ip_in_subnet,
    first_enum,
    normalize_allocated_status,
    required_asset_permission,
    user_has_asset_permission,
    validate_ip_belongs_to_subnet,
)

pytestmark = pytest.mark.unit

SUBNET = {"_id": 9, "subnet_address": "10.11.27.0", "subnet_mask": "24"}


def test_first_enum_reads_list_or_scalar():
    assert first_enum(["allocated"]) == "allocated"
    assert first_enum("reserved") == "reserved"
    assert first_enum([]) is None
    assert first_enum(None) is None


def test_normalize_allocated_status_rejects_empty():
    with pytest.raises(IpamEditError):
        normalize_allocated_status("")
    with pytest.raises(IpamEditError):
        normalize_allocated_status([])
    assert normalize_allocated_status("allocated") == "allocated"
    assert normalize_allocated_status(["reserved"]) == "reserved"


def test_decide_create_update_delete_noop():
    assert decide_manual_ip_action(None, "allocated") == ACTION_CREATE
    assert decide_manual_ip_action({"_id": 1}, "reserved") == ACTION_UPDATE
    assert decide_manual_ip_action({"_id": 1}, "available") == ACTION_DELETE
    assert decide_manual_ip_action(None, "available") == ACTION_NOOP


def test_required_asset_permission_matches_action():
    assert required_asset_permission(ACTION_CREATE) == "asset_info-Add"
    assert required_asset_permission(ACTION_UPDATE) == "asset_info-Edit"
    assert required_asset_permission(ACTION_DELETE) == "asset_info-Delete"
    assert required_asset_permission(ACTION_NOOP) is None


def test_find_ip_in_subnet_matches_address():
    ips = [{"ip_addr": "10.11.27.10", "_id": 1}, {"ip_addr": "10.11.27.11", "_id": 2}]
    assert find_ip_in_subnet(ips, " 10.11.27.11 ")["_id"] == 2
    assert find_ip_in_subnet(ips, "10.11.27.99") is None


def test_validate_ip_belongs_to_subnet():
    validate_ip_belongs_to_subnet("10.11.27.87", SUBNET)
    with pytest.raises(IpamEditError):
        validate_ip_belongs_to_subnet("10.11.28.1", SUBNET)
    with pytest.raises(IpamEditError):
        validate_ip_belongs_to_subnet("10.11.27.0", SUBNET)
    with pytest.raises(IpamEditError):
        validate_ip_belongs_to_subnet("10.11.27.255", SUBNET)
    with pytest.raises(IpamEditError):
        validate_ip_belongs_to_subnet("", SUBNET)


def test_user_has_asset_permission():
    class User:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    assert user_has_asset_permission(User(is_superuser=True, permission={}), "asset_info-Edit")
    assert user_has_asset_permission(
        User(is_superuser=False, permission={"cmdb": {"asset_info-Edit"}}),
        "asset_info-Edit",
    )
    assert not user_has_asset_permission(
        User(is_superuser=False, permission={"cmdb": {"asset_info-View"}}),
        "asset_info-Edit",
    )


def test_execute_create_marks_manual_and_unknown_status(monkeypatch):
    from apps.cmdb.services import ipam_edit as svc

    created = {"_id": 4, "inst_uuid": "new-ip", "ip_addr": "10.11.27.10"}
    captured = {}

    class InstanceManage:
        @staticmethod
        def instance_create(model_id, payload, operator, allowed_org_ids=None):
            captured["payload"] = payload
            captured["operator"] = operator
            return created

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", InstanceManage)
    monkeypatch.setattr("apps.cmdb.services.ipam_discovery._ensure_subnet_ip_association", lambda *a, **k: None)
    monkeypatch.setattr(svc, "_safe_writeback", lambda *a, **k: None)

    result = svc.execute_manual_ip_action(
        action="create",
        subnet=SUBNET,
        existing=None,
        ip_addr="10.11.27.10",
        allocated_status="allocated",
        ip_status="offline",
        ip_type="static",
        ip_user=["alice"],
        mac="AA:BB:CC:DD:EE:FF",
        description="web vip",
        operator="bob",
        allowed_org_ids=[1],
        user_groups=[],
        roles=[],
    )
    assert result["action"] == "create"
    assert captured["payload"]["auto_collect"] is False
    assert captured["payload"]["ip_status"] == ["offline"]
    assert captured["payload"]["ip_allocated_status"] == ["allocated"]
    assert captured["payload"]["ip_type"] == ["static"]
    assert captured["payload"]["ip_user"] == ["alice"]
    assert captured["payload"]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert captured["payload"]["description"] == "web vip"
    assert captured["operator"] == "bob"


def test_execute_create_rolls_back_when_association_fails(monkeypatch):
    from apps.cmdb.services import ipam_edit as svc

    created = {"_id": 4, "inst_uuid": "new-ip", "ip_addr": "10.11.27.10"}
    captured = {}

    class InstanceManage:
        @staticmethod
        def instance_create(model_id, payload, operator, allowed_org_ids=None):
            return created

        @staticmethod
        def instance_batch_delete_by_uuids(user_groups, roles, uuids, operator):
            captured["deleted"] = uuids

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", InstanceManage)
    monkeypatch.setattr(
        "apps.cmdb.services.ipam_discovery._ensure_subnet_ip_association",
        lambda *a, **k: {"success": [], "failed": [{"error": "graph down"}]},
    )
    monkeypatch.setattr(svc, "_safe_writeback", lambda *a, **k: captured.setdefault("writeback", True))

    with pytest.raises(IpamEditError, match="graph down"):
        svc.execute_manual_ip_action(
            action="create",
            subnet=SUBNET,
            existing=None,
            ip_addr="10.11.27.10",
            allocated_status="allocated",
            operator="bob",
            allowed_org_ids=[1],
            user_groups=[],
            roles=[],
        )
    assert captured["deleted"] == ["new-ip"]
    assert "writeback" not in captured


def test_execute_update_raises_when_association_fails(monkeypatch):
    from apps.cmdb.services import ipam_edit as svc

    existing = {"_id": 7, "inst_uuid": "ip-7", "ip_addr": "10.11.27.10"}

    class InstanceManage:
        @staticmethod
        def instance_update(user_groups, roles, inst_id, update_attr, operator, allowed_org_ids=None):
            return {**existing, **update_attr}

        @staticmethod
        def instance_batch_delete_by_uuids(*args, **kwargs):
            raise AssertionError("update 失败不应删除已有 IP")

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", InstanceManage)
    monkeypatch.setattr(
        "apps.cmdb.services.ipam_discovery._ensure_subnet_ip_association",
        lambda *a, **k: {"success": [], "failed": [{"error": "assoc failed"}]},
    )

    with pytest.raises(IpamEditError, match="assoc failed"):
        svc.execute_manual_ip_action(
            action="update",
            subnet=SUBNET,
            existing=existing,
            ip_addr="10.11.27.10",
            allocated_status="reserved",
            operator="bob",
            allowed_org_ids=[1],
            user_groups=[],
            roles=[],
        )


def test_build_editable_ip_attrs_defaults_unknown_on_create():
    from apps.cmdb.services.ipam_edit import build_editable_ip_attrs

    created = build_editable_ip_attrs(allocated_status="allocated", for_create=True)
    assert created["ip_status"] == ["unknown"]
    assert created["ip_type"] == []
    assert created["description"] == ""
    updated = build_editable_ip_attrs(
        allocated_status="reserved",
        ip_status="online",
        description="vip",
    )
    assert updated["ip_status"] == ["online"]
    assert updated["description"] == "vip"
