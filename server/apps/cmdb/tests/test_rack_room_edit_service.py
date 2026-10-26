# -- coding: utf-8 --
"""机房机柜布局编辑纯逻辑。"""
from contextlib import contextmanager

import pytest

from apps.cmdb.services.rack_room_edit import (
    ACTION_PLACE_CREATE,
    ACTION_PLACE_EXISTING,
    ACTION_UNPLACE,
    CANDIDATE_ALREADY_PLACED,
    CANDIDATE_OCCUPIED,
    CANDIDATE_SELECTABLE,
    PLACEABLE_DEVICE_MODELS,
    RackRoomEditError,
    cell_is_occupied,
    classify_device_candidate,
    classify_rack_candidate,
    device_place_attrs,
    device_u_conflict,
    device_unplace_attrs,
    has_device_u_start,
    has_valid_rack_location,
    model_asst_id,
    normalize_device_u_size,
    rack_place_attrs,
    rack_unplace_attrs,
    required_asset_permission,
    user_has_asset_permission,
)
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit


def test_classify_rack_candidate_scope():
    assert classify_rack_candidate(1, [], False) == CANDIDATE_SELECTABLE
    assert classify_rack_candidate(1, [1], False) == CANDIDATE_SELECTABLE
    assert classify_rack_candidate(1, [1], True) == CANDIDATE_ALREADY_PLACED
    assert classify_rack_candidate(1, [2], False) == CANDIDATE_OCCUPIED
    assert classify_rack_candidate(1, [2], True) == CANDIDATE_OCCUPIED


def test_classify_device_candidate_scope():
    assert classify_device_candidate(9, [], False) == CANDIDATE_SELECTABLE
    assert classify_device_candidate(9, [9], False) == CANDIDATE_SELECTABLE
    assert classify_device_candidate(9, [9], True) == CANDIDATE_ALREADY_PLACED
    assert classify_device_candidate(9, [8], True) == CANDIDATE_OCCUPIED


def test_has_valid_rack_location_uses_label():
    assert has_valid_rack_location({"location": "A03"}) is True
    assert has_valid_rack_location({"location": "A3"}) is True
    assert has_valid_rack_location({"location": ""}) is False
    assert has_valid_rack_location({"location": "3A"}) is False
    assert has_device_u_start({"rack_u_start": 4}) is True
    assert has_device_u_start({"rack_u_start": 0}) is False


def test_cell_occupied_and_u_overlap():
    racks = [{"inst_id": "1", "row": 2, "col": 3}]
    assert cell_is_occupied(racks, 2, 3) is True
    assert cell_is_occupied(racks, 2, 3, exclude_inst_id="1") is False
    assert cell_is_occupied(racks, 1, 1) is False
    placed = [{"inst_id": "d1", "rack_u_start": 10, "u_size": 2}]
    assert device_u_conflict(placed, 10, 2, 42) == "U 位与已有设备重叠"
    assert device_u_conflict(placed, 12, 2, 42) is None
    assert device_u_conflict(placed, 41, 3, 42) == "设备超出机柜 U 位"
    assert device_u_conflict(placed, 10, 2, 42, exclude_inst_id="d1") is None
    assert device_u_conflict([], 1, 1, 0) == "机柜未配置总 U 数"


def test_place_and_unplace_attrs_only_touch_layout_fields():
    placed = rack_place_attrs(1, 3)
    assert placed == {"location": "C01"}
    assert "row" not in placed
    assert "col" not in placed
    cleared = rack_unplace_attrs()
    assert cleared == {"location": ""}
    assert device_place_attrs(8, 2) == {"rack_u_start": 8, "u_size": 2}
    assert device_unplace_attrs() == {"rack_u_start": ""}
    assert "u_size" not in device_unplace_attrs()
    assert normalize_device_u_size(None) == 1
    assert normalize_device_u_size(4) == 4
    with pytest.raises(RackRoomEditError):
        rack_place_attrs(0, 1)


def test_required_permission_and_allowed_models():
    assert required_asset_permission(ACTION_PLACE_CREATE) == "asset_info-Add"
    assert required_asset_permission(ACTION_PLACE_EXISTING) == "asset_info-Edit"
    assert required_asset_permission(ACTION_UNPLACE) == "asset_info-Edit"
    assert "host" not in PLACEABLE_DEVICE_MODELS
    assert model_asst_id("server_room", "run", "rack") == "server_room_run_rack"
    assert model_asst_id("rack", "contains", "switch") == "rack_contains_switch"


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


def test_execute_place_create_rack_writes_location_and_association(monkeypatch):
    from apps.cmdb.services import rack_room_edit as svc

    created = {"_id": 4, "inst_uuid": "rack-new", "model_id": "rack", "inst_name": "R1"}
    captured = {}

    class InstanceManage:
        @staticmethod
        def instance_create(model_id, payload, operator, allowed_org_ids=None):
            captured["payload"] = payload
            captured["model_id"] = model_id
            return created

        @staticmethod
        def instance_association_create(data, operator):
            captured["assoc"] = data

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", InstanceManage)
    monkeypatch.setattr("apps.cmdb.services.rack_room.get_room_layout", lambda *a, **k: {"racks": []})

    result = svc.execute_layout_action(
        action=ACTION_PLACE_CREATE,
        scope="room",
        container={"_id": 1, "model_id": "server_room", "inst_uuid": "room-1"},
        operator="bob",
        allowed_org_ids=[1],
        user_groups=[],
        roles=[],
        instance_info={
            "inst_name": "R1",
            "u_count": 42,
            "organization": [1],
            "row": 9,
            "col": 9,
        },
        row=2,
        col=1,
    )
    assert result["action"] == ACTION_PLACE_CREATE
    assert captured["model_id"] == "rack"
    assert captured["payload"]["location"] == "A02"
    assert "row" not in captured["payload"]
    assert "col" not in captured["payload"]
    assert captured["assoc"]["model_asst_id"] == "server_room_run_rack"


def test_execute_place_existing_rejects_other_room(monkeypatch):
    from apps.cmdb.services import rack_room_edit as svc

    existing = {"_id": 8, "inst_uuid": "rack-8", "model_id": "rack", "location": ""}

    class InstanceManage:
        @staticmethod
        def instance_association_map(model_id, inst_ids, related_model=None):
            return {8: [99]}

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", InstanceManage)
    monkeypatch.setattr("apps.cmdb.services.rack_room.get_room_layout", lambda *a, **k: {"racks": []})
    with pytest.raises(RackRoomEditError, match="其他机房"):
        svc.execute_layout_action(
            action=ACTION_PLACE_EXISTING,
            scope="room",
            container={"_id": 1, "model_id": "server_room", "inst_uuid": "room-1"},
            operator="bob",
            allowed_org_ids=[1],
            user_groups=[],
            roles=[],
            existing=existing,
            row=1,
            col=1,
        )


def test_execute_unplace_rack_clears_location_keeps_instance(monkeypatch):
    from apps.cmdb.services import rack_room_edit as svc

    existing = {
        "_id": 8,
        "inst_uuid": "rack-8",
        "model_id": "rack",
        "inst_name": "R1",
        "u_count": 42,
        "location": "A02",
    }
    captured = {}

    class InstanceManage:
        @staticmethod
        def instance_association_map(model_id, inst_ids, related_model=None):
            return {8: [1]}

        @staticmethod
        def instance_association_delete_by_key(**kwargs):
            captured["delete"] = kwargs

        @staticmethod
        def instance_update(user_groups, roles, inst_id, update_attr, operator, allowed_org_ids=None):
            captured["update"] = update_attr
            return {**existing, **update_attr}

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", InstanceManage)
    monkeypatch.setattr("apps.cmdb.services.rack_room.get_room_layout", lambda *a, **k: {"racks": []})
    result = svc.execute_layout_action(
        action=ACTION_UNPLACE,
        scope="room",
        container={"_id": 1, "model_id": "server_room", "inst_uuid": "room-1"},
        operator="bob",
        allowed_org_ids=[1],
        user_groups=[],
        roles=[],
        existing=existing,
    )
    assert result["action"] == ACTION_UNPLACE
    assert captured["update"] == {"location": ""}
    assert "u_count" not in captured["update"]
    assert "row" not in captured["update"]
    assert "col" not in captured["update"]
    assert captured["delete"]["model_asst_id"] == "server_room_run_rack"


def test_execute_unplace_device_clears_start_keeps_u_size(monkeypatch):
    from apps.cmdb.services import rack_room_edit as svc

    _install_passthrough_rack_lock(monkeypatch)

    existing = {
        "_id": 11,
        "inst_uuid": "sw-1",
        "model_id": "switch",
        "rack_u_start": 10,
        "u_size": 2,
        "inst_name": "sw",
    }
    captured = {}

    class InstanceManage:
        @staticmethod
        def instance_association_map(model_id, inst_ids, related_model=None):
            return {11: [9]}

        @staticmethod
        def instance_association_delete_by_key(**kwargs):
            captured["delete"] = kwargs

        @staticmethod
        def instance_update(user_groups, roles, inst_id, update_attr, operator, allowed_org_ids=None):
            captured["update"] = update_attr
            return {**existing, **update_attr}

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", InstanceManage)
    monkeypatch.setattr(
        "apps.cmdb.services.rack_room.get_rack_layout",
        lambda *a, **k: {"rack": {"u_count": 42}, "placed": []},
    )
    result = svc.execute_layout_action(
        action=ACTION_UNPLACE,
        scope="rack",
        container={"_id": 9, "model_id": "rack", "inst_uuid": "rack-9", "u_count": 42},
        operator="bob",
        allowed_org_ids=[1],
        user_groups=[],
        roles=[],
        existing=existing,
    )
    assert result["action"] == ACTION_UNPLACE
    assert captured["update"] == {"rack_u_start": ""}
    assert "u_size" not in captured["update"]
    assert captured["delete"]["model_asst_id"] == "rack_contains_switch"


def test_execute_unplace_rack_rejects_other_room(monkeypatch):
    from apps.cmdb.services import rack_room_edit as svc

    existing = {
        "_id": 8,
        "inst_uuid": "rack-8",
        "model_id": "rack",
        "location": "A02",
    }
    captured = {}

    class InstanceManage:
        @staticmethod
        def instance_association_map(model_id, inst_ids, related_model=None):
            return {8: [99]}

        @staticmethod
        def instance_association_delete_by_key(**kwargs):
            captured["delete"] = kwargs

        @staticmethod
        def instance_update(*args, **kwargs):
            captured["update"] = True

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", InstanceManage)
    with pytest.raises(RackRoomEditError, match="当前机房"):
        svc.execute_layout_action(
            action=ACTION_UNPLACE,
            scope="room",
            container={"_id": 1, "model_id": "server_room", "inst_uuid": "room-1"},
            operator="bob",
            allowed_org_ids=[1],
            user_groups=[],
            roles=[],
            existing=existing,
        )
    assert "delete" not in captured
    assert "update" not in captured


def test_execute_unplace_device_rejects_other_rack(monkeypatch):
    from apps.cmdb.services import rack_room_edit as svc

    _install_passthrough_rack_lock(monkeypatch)

    existing = {
        "_id": 11,
        "inst_uuid": "sw-1",
        "model_id": "switch",
        "rack_u_start": 10,
        "u_size": 2,
    }
    captured = {}

    class InstanceManage:
        @staticmethod
        def instance_association_map(model_id, inst_ids, related_model=None):
            return {11: [8]}

        @staticmethod
        def instance_association_delete_by_key(**kwargs):
            captured["delete"] = kwargs

        @staticmethod
        def instance_update(*args, **kwargs):
            captured["update"] = True

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", InstanceManage)
    with pytest.raises(RackRoomEditError, match="当前机柜"):
        svc.execute_layout_action(
            action=ACTION_UNPLACE,
            scope="rack",
            container={"_id": 9, "model_id": "rack", "inst_uuid": "rack-9", "u_count": 42},
            operator="bob",
            allowed_org_ids=[1],
            user_groups=[],
            roles=[],
            existing=existing,
        )
    assert "delete" not in captured
    assert "update" not in captured


def test_execute_place_device_rejects_host(monkeypatch):
    from apps.cmdb.services import rack_room_edit as svc

    _install_passthrough_rack_lock(monkeypatch)

    monkeypatch.setattr(
        "apps.cmdb.services.rack_room.get_rack_layout",
        lambda *a, **k: {"rack": {"u_count": 42}, "placed": []},
    )
    with pytest.raises(RackRoomEditError, match="不能放置"):
        svc.execute_layout_action(
            action=ACTION_PLACE_CREATE,
            scope="rack",
            container={"_id": 9, "model_id": "rack", "inst_uuid": "rack-9", "u_count": 42},
            operator="bob",
            allowed_org_ids=[1],
            user_groups=[],
            roles=[],
            model_id="host",
            instance_info={"inst_name": "h1"},
            u_start=1,
            u_size=1,
        )


RACK_UUID = "rack-9"
OTHER_RACK_UUID = "rack-8"
_OCCUPIED_SWITCH = {"inst_id": "sw-occupied", "model_id": "switch", "rack_u_start": 10, "u_size": 2}


class _RackLockDouble:
    """进入含目标机柜 inst_uuid 的锁之后，布局才能看到 U10 上的 switch。"""

    def __init__(self):
        self.held_keys: set[str] = set()
        self.busy_uuids: set[str] = set()
        self.hold_calls: list[list[str]] = []
        self.locked_reads = 0

    def holds(self, inst_uuid: str) -> bool:
        return any(inst_uuid in key for key in self.held_keys)

    def install(self, monkeypatch):
        state = self

        @contextmanager
        def hold(lock_keys, *, lease_seconds=None):
            keys = [str(key) for key in (lock_keys or [])]
            state.hold_calls.append(keys)
            if any(uuid in key for key in keys for uuid in state.busy_uuids):
                raise BaseAppException("相同唯一键正在写入，请稍后重试")
            for key in keys:
                state.held_keys.add(key)
            try:
                yield "owner"
            finally:
                for key in keys:
                    state.held_keys.discard(key)

        monkeypatch.setattr("apps.cmdb.services.unique_write_lock.UniqueWriteLockService.hold", hold)


@contextmanager
def _passthrough_rack_lock(lock_keys, *, lease_seconds=None):
    yield "passthrough"


def _install_passthrough_rack_lock(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.unique_write_lock.UniqueWriteLockService.hold",
        _passthrough_rack_lock,
    )


def _device(inst_id, inst_uuid, model_id, u_size=1):
    return {
        "_id": inst_id,
        "inst_uuid": inst_uuid,
        "model_id": model_id,
        "inst_name": model_id,
        "u_size": u_size,
    }


def _layout_after_lock(state: _RackLockDouble, rack_uuid: str):
    def get_rack_layout(*_args, **_kwargs):
        if state.holds(rack_uuid):
            state.locked_reads += 1
            return {"rack": {"u_count": 42}, "placed": [dict(_OCCUPIED_SWITCH)]}
        return {"rack": {"u_count": 42}, "placed": []}

    return get_rack_layout


def _place_existing(monkeypatch, state: _RackLockDouble, *, existing, u_start, u_size, captured, rack_uuid=RACK_UUID):
    from apps.cmdb.services import rack_room_edit as svc

    class InstanceManage:
        @staticmethod
        def instance_association_map(model_id, inst_ids, related_model=None):
            return {}

        @staticmethod
        def instance_update(user_groups, roles, inst_id, update_attr, operator, allowed_org_ids=None):
            captured["update"] = update_attr
            captured["locked_update"] = state.holds(rack_uuid)
            return {**existing, **update_attr}

        @staticmethod
        def instance_association_create(data, operator):
            captured["assoc"] = data
            captured["locked_assoc"] = state.holds(rack_uuid)

    state.install(monkeypatch)
    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage", InstanceManage)
    monkeypatch.setattr("apps.cmdb.services.rack_room.get_rack_layout", _layout_after_lock(state, rack_uuid))
    return svc.execute_layout_action(
        action=ACTION_PLACE_EXISTING,
        scope="rack",
        container={"_id": 9, "model_id": "rack", "inst_uuid": rack_uuid, "u_count": 42},
        operator="bob",
        allowed_org_ids=[1],
        user_groups=[],
        roles=[],
        existing=existing,
        u_start=u_start,
        u_size=u_size,
    )


def test_place_existing_same_u_reads_occupancy_only_inside_rack_lock(monkeypatch):
    state = _RackLockDouble()
    router = _device(21, "router-1", "router", u_size=2)
    captured = {}
    with pytest.raises(RackRoomEditError, match="U 位与已有设备重叠"):
        _place_existing(
            monkeypatch,
            state,
            existing=router,
            u_start=10,
            u_size=2,
            captured=captured,
        )
    assert state.locked_reads >= 1
    assert captured.get("update") is None
    assert captured.get("assoc") is None


def test_sequential_place_into_empty_u_holds_rack_lock_through_write(monkeypatch):
    state = _RackLockDouble()
    switch = _device(11, "sw-1", "switch")
    router = _device(21, "router-1", "router")
    first_captured = {}
    second_captured = {}
    first = _place_existing(
        monkeypatch,
        state,
        existing=switch,
        u_start=1,
        u_size=1,
        captured=first_captured,
    )
    second = _place_existing(
        monkeypatch,
        state,
        existing=router,
        u_start=3,
        u_size=1,
        captured=second_captured,
    )
    assert first["action"] == ACTION_PLACE_EXISTING
    assert second["action"] == ACTION_PLACE_EXISTING
    assert first_captured["update"] == {"rack_u_start": 1, "u_size": 1}
    assert second_captured["update"] == {"rack_u_start": 3, "u_size": 1}
    assert first_captured["locked_update"] is True
    assert first_captured["locked_assoc"] is True
    assert second_captured["locked_update"] is True
    assert second_captured["locked_assoc"] is True
    assert first_captured["assoc"]["model_asst_id"] == "rack_contains_switch"
    assert second_captured["assoc"]["model_asst_id"] == "rack_contains_router"
    assert state.locked_reads >= 1


def test_other_rack_lock_does_not_block_device_place(monkeypatch):
    state = _RackLockDouble()
    state.busy_uuids.add(OTHER_RACK_UUID)
    router = _device(21, "router-1", "router", u_size=2)
    captured = {}
    result = _place_existing(
        monkeypatch,
        state,
        existing=router,
        u_start=12,
        u_size=2,
        captured=captured,
    )
    assert result["action"] == ACTION_PLACE_EXISTING
    assert captured["update"] == {"rack_u_start": 12, "u_size": 2}
    assert captured["locked_update"] is True
    assert captured["locked_assoc"] is True
    assert state.hold_calls
    assert all(RACK_UUID in key for keys in state.hold_calls for key in keys)
    assert all(OTHER_RACK_UUID not in key for keys in state.hold_calls for key in keys)


def test_busy_same_rack_lock_retries_without_writing(monkeypatch):
    state = _RackLockDouble()
    state.busy_uuids.add(RACK_UUID)
    router = _device(21, "router-1", "router", u_size=2)
    captured = {}
    with pytest.raises(BaseAppException, match="相同唯一键正在写入，请稍后重试"):
        _place_existing(
            monkeypatch,
            state,
            existing=router,
            u_start=12,
            u_size=2,
            captured=captured,
        )
    assert captured.get("update") is None
    assert captured.get("assoc") is None
