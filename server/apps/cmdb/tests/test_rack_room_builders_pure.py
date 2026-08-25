import pytest

from apps.cmdb.services.rack_room import build_rack_layout, build_room_layout, col_to_letter, format_rack_location_label, parse_rack_location


def _uuid(value: int) -> str:
    return f"00000000-0000-4000-8000-{value:012d}"


@pytest.mark.unit
def test_col_to_letter():
    assert col_to_letter(1) == "A"
    assert col_to_letter(12) == "L"
    assert col_to_letter(27) == "AA"


@pytest.mark.unit
def test_parse_rack_location_letter_is_col_number_is_row():
    # 与俯视图一致：字母=列（横轴），数字=行（纵轴）
    assert parse_rack_location("A01") == (1, 1)
    assert parse_rack_location("B01") == (1, 2)
    assert parse_rack_location("C01") == (1, 3)
    assert parse_rack_location("A09") == (9, 1)
    assert parse_rack_location("A3") == (3, 1)
    assert parse_rack_location("B21") == (21, 2)
    assert parse_rack_location("R01-14") is None
    assert parse_rack_location("") is None
    assert parse_rack_location(None) is None


@pytest.mark.unit
def test_format_rack_location_label_round_trip():
    assert format_rack_location_label(1, 1) == "A01"
    assert format_rack_location_label(1, 2) == "B01"
    assert format_rack_location_label(9, 1) == "A09"
    assert format_rack_location_label(3, 1) == "A03"
    assert parse_rack_location(format_rack_location_label(21, 2)) == (21, 2)


@pytest.mark.unit
def test_build_room_layout_places_and_collects_unplaced_and_conflicts():
    racks = [
        {"inst_uuid": _uuid(1), "inst_name": "A01", "row": 1, "col": 1, "u_count": 42, "datacenter_type": "1", "datacenter_state": "1", "used_u": 21},
        {"inst_uuid": _uuid(2), "inst_name": "A02", "row": 2, "col": 1, "u_count": 42, "datacenter_type": "1", "datacenter_state": "1", "used_u": 0},
        {"inst_uuid": _uuid(3), "inst_name": "B01", "row": 1, "col": 1, "u_count": 42, "datacenter_type": "2", "datacenter_state": "1", "used_u": 10},
        {
            "inst_uuid": _uuid(4),
            "inst_name": "未定位",
            "row": None,
            "col": None,
            "u_count": 42,
            "datacenter_type": "1",
            "datacenter_state": "1",
            "used_u": 0,
        },
    ]
    out = build_room_layout(racks)
    assert {r["inst_uuid"] for r in out["racks"]} == {_uuid(1), _uuid(2), _uuid(3)}
    assert [r["inst_uuid"] for r in out["unplaced"]] == [_uuid(4)]
    placed1 = next(r for r in out["racks"] if r["inst_uuid"] == _uuid(1))
    assert placed1["col_letter"] == "A"
    assert placed1["usage"] == 50
    assert out["conflicts"] == [{"row": 1, "col": 1, "inst_uuids": [_uuid(1), _uuid(3)]}]
    assert out["grid"] == {"max_row": 2, "max_col": 1}
    placed2 = next(r for r in out["racks"] if r["inst_uuid"] == _uuid(2))
    assert placed2["usage"] == 0  # used_u=0 → 0%


@pytest.mark.unit
def test_build_room_layout_zero_u_count_guards_division():
    racks = [
        {"inst_uuid": _uuid(9), "inst_name": "无U数", "row": 1, "col": 2, "u_count": 0, "datacenter_type": "1", "datacenter_state": "1", "used_u": 0},
    ]
    out = build_room_layout(racks)
    assert out["racks"][0]["usage"] == 0  # u_count=0 不应除零，回退 0%
    assert out["racks"][0]["col_letter"] == "B"


@pytest.mark.unit
def test_build_room_layout_partial_position_is_unplaced():
    racks = [
        {
            "inst_uuid": _uuid(7),
            "inst_name": "位置为空",
            "row": None,
            "col": None,
            "location": "",
            "u_count": 42,
            "datacenter_type": "1",
            "datacenter_state": "1",
            "used_u": 0,
        },
        {
            "inst_uuid": _uuid(8),
            "inst_name": "位置格式错误",
            "row": None,
            "col": None,
            "location": "R01-14",
            "u_count": 42,
            "datacenter_type": "1",
            "datacenter_state": "1",
            "used_u": 0,
        },
    ]
    out = build_room_layout(racks)
    assert out["racks"] == []
    assert [(r["inst_uuid"], r["unplaced_reason"]) for r in out["unplaced"]] == [
        (_uuid(7), "missing_location"),
        (_uuid(8), "invalid_location"),
    ]


@pytest.mark.unit
def test_build_rack_layout_placed_unplaced_overflow_overlap():
    devices = [
        {"inst_uuid": _uuid(10), "inst_name": "sw", "model_id": "switch", "rack_u_start": 41, "u_size": 2},
        {"inst_uuid": _uuid(11), "inst_name": "srv", "model_id": "physcial_server", "rack_u_start": 42, "u_size": 2},
        {"inst_uuid": _uuid(12), "inst_name": "no-u", "model_id": "switch", "rack_u_start": None, "u_size": None},
    ]
    out = build_rack_layout(42, devices)
    assert out["u_count"] == 42
    assert [d["inst_uuid"] for d in out["unplaced"]] == [_uuid(12)]
    placed = {d["inst_uuid"]: d for d in out["placed"]}
    assert placed[_uuid(10)]["u_end"] == 42 and placed[_uuid(10)]["overflow"] is False
    assert placed[_uuid(11)]["u_end"] == 43 and placed[_uuid(11)]["overflow"] is True
    assert [_uuid(10), _uuid(11)] in out["overlaps"]


@pytest.mark.unit
def test_build_rack_layout_free_and_max_contiguous():
    # u_count=10，设备占 U3-5；空闲 = {1,2,6,7,8,9,10}=7，最大连续空闲 = 6-10 = 5
    devices = [
        {"inst_uuid": _uuid(1), "inst_name": "srv", "model_id": "physcial_server", "rack_u_start": 3, "u_size": 3},
    ]
    out = build_rack_layout(10, devices)
    assert out["free_u"] == 7
    assert out["max_free_u"] == 5
