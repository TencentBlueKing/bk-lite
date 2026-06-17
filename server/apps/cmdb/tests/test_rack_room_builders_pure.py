import pytest
from apps.cmdb.services.rack_room import col_to_letter, build_room_layout
from apps.cmdb.services.rack_room import build_rack_layout


@pytest.mark.unit
def test_col_to_letter():
    assert col_to_letter(1) == "A"
    assert col_to_letter(12) == "L"
    assert col_to_letter(27) == "AA"


@pytest.mark.unit
def test_build_room_layout_places_and_collects_unplaced_and_conflicts():
    racks = [
        {"inst_id": "1", "inst_name": "A01", "row": 1, "col": 1,
         "u_count": 42, "datacenter_type": "1", "datacenter_state": "1", "used_u": 21},
        {"inst_id": "2", "inst_name": "A02", "row": 2, "col": 1,
         "u_count": 42, "datacenter_type": "1", "datacenter_state": "1", "used_u": 0},
        {"inst_id": "3", "inst_name": "B01", "row": 1, "col": 1,
         "u_count": 42, "datacenter_type": "2", "datacenter_state": "1", "used_u": 10},
        {"inst_id": "4", "inst_name": "未定位", "row": None, "col": None,
         "u_count": 42, "datacenter_type": "1", "datacenter_state": "1", "used_u": 0},
    ]
    out = build_room_layout(racks)
    assert {r["inst_id"] for r in out["racks"]} == {"1", "2", "3"}
    assert [r["inst_id"] for r in out["unplaced"]] == ["4"]
    placed1 = next(r for r in out["racks"] if r["inst_id"] == "1")
    assert placed1["col_letter"] == "A"
    assert placed1["usage"] == 50
    assert out["conflicts"] == [{"row": 1, "col": 1, "inst_ids": ["1", "3"]}]
    assert out["grid"] == {"max_row": 2, "max_col": 1}
    placed2 = next(r for r in out["racks"] if r["inst_id"] == "2")
    assert placed2["usage"] == 0  # used_u=0 → 0%


@pytest.mark.unit
def test_build_room_layout_zero_u_count_guards_division():
    racks = [
        {"inst_id": "9", "inst_name": "无U数", "row": 1, "col": 2,
         "u_count": 0, "datacenter_type": "1", "datacenter_state": "1", "used_u": 0},
    ]
    out = build_room_layout(racks)
    assert out["racks"][0]["usage"] == 0  # u_count=0 不应除零，回退 0%
    assert out["racks"][0]["col_letter"] == "B"


@pytest.mark.unit
def test_build_room_layout_partial_position_is_unplaced():
    # 只有 row 没有 col → 未定位
    racks = [
        {"inst_id": "7", "inst_name": "半坐标", "row": 1, "col": None,
         "u_count": 42, "datacenter_type": "1", "datacenter_state": "1", "used_u": 0},
    ]
    out = build_room_layout(racks)
    assert out["racks"] == []
    assert [r["inst_id"] for r in out["unplaced"]] == ["7"]


@pytest.mark.unit
def test_build_rack_layout_placed_unplaced_overflow_overlap():
    devices = [
        {"inst_id": "10", "inst_name": "sw", "model_id": "switch",
         "rack_u_start": 41, "u_size": 2},
        {"inst_id": "11", "inst_name": "srv", "model_id": "physcial_server",
         "rack_u_start": 42, "u_size": 2},
        {"inst_id": "12", "inst_name": "no-u", "model_id": "switch",
         "rack_u_start": None, "u_size": None},
    ]
    out = build_rack_layout(42, devices)
    assert out["u_count"] == 42
    assert [d["inst_id"] for d in out["unplaced"]] == ["12"]
    placed = {d["inst_id"]: d for d in out["placed"]}
    assert placed["10"]["u_end"] == 42 and placed["10"]["overflow"] is False
    assert placed["11"]["u_end"] == 43 and placed["11"]["overflow"] is True
    assert ["10", "11"] in out["overlaps"]


@pytest.mark.unit
def test_build_rack_layout_free_and_max_contiguous():
    # u_count=10，设备占 U3-5；空闲 = {1,2,6,7,8,9,10}=7，最大连续空闲 = 6-10 = 5
    devices = [
        {"inst_id": "1", "inst_name": "srv", "model_id": "physcial_server",
         "rack_u_start": 3, "u_size": 3},
    ]
    out = build_rack_layout(10, devices)
    assert out["free_u"] == 7
    assert out["max_free_u"] == 5
