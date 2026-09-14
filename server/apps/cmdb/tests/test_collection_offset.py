"""采集启动相位分配：多组数据可见性测试。"""

from __future__ import annotations

import pytest

from apps.cmdb.services.collection_offset import (
    CollectionSchedule,
    assign_many,
    assign_offset,
    exact_start_collisions,
    fire_starts,
    occupancy_width_minutes,
    planning_horizon_minutes,
    same_cycle_start_collisions,
)

pytestmark = pytest.mark.unit


def _print_group(title: str, schedules: list[CollectionSchedule]) -> None:
    horizon = planning_horizon_minutes([item.cycle_minutes for item in schedules])
    collisions = exact_start_collisions(schedules, horizon_minutes=horizon)
    same_cycle = same_cycle_start_collisions(schedules)
    print(f"\n======== {title} ========")
    print(f"{'task':>6} {'cycle':>7} {'targets':>8} {'width':>6} " f"{'offset_min':>11} {'offset_sec':>11} {'interval_sec':>13}  fires_in_horizon")
    for item in schedules:
        fires = fire_starts(item.offset_minutes, item.cycle_minutes, min(horizon, item.cycle_minutes * 3))
        fire_text = ",".join(str(minute) for minute in fires[:8])
        if len(fires) > 8:
            fire_text += ",..."
        print(
            f"{item.task_id:>6} {item.cycle_minutes:>7} {item.target_count:>8} "
            f"{item.width_minutes:>6} {item.offset_minutes:>11} "
            f"{item.collection_offset_seconds:>11} {item.interval_seconds:>13}  {fire_text}"
        )
    print(f"planning_horizon_minutes={horizon}")
    print(f"exact_start_collisions={collisions[:12] or '[]'}")
    if len(collisions) > 12:
        print(f"  ... total {len(collisions)} collision minutes")
    print(f"same_cycle_same_offset={same_cycle or '[]'}")


def test_occupancy_width_buckets():
    assert occupancy_width_minutes(20, 30) == 5
    assert occupancy_width_minutes(200, 30) == 10
    assert occupancy_width_minutes(800, 30) == 15
    assert occupancy_width_minutes(2048, 30) == 20
    assert occupancy_width_minutes(2048, 220) == 20


def test_group_10_small_30min_unique_starts():
    schedules = assign_many([(index, 30, 20) for index in range(1, 11)])
    _print_group("G1 10条小任务 全 30min / 20 targets", schedules)
    offsets = [item.offset_minutes for item in schedules]
    assert all(0 <= item.offset_minutes < 30 for item in schedules)
    assert len(set(offsets)) == 10
    assert same_cycle_start_collisions(schedules) == []


def test_group_two_large_then_small_30min():
    requests = [(1, 30, 2048), (2, 30, 2048), *[(index, 30, 200) for index in range(3, 8)]]
    schedules = assign_many(requests)
    _print_group("G2 先两条 /21(2048) 再五条 /24(200) 全 30min", schedules)
    large = [item for item in schedules if item.target_count == 2048]
    assert len(large) == 2
    gap = abs(large[0].offset_minutes - large[1].offset_minutes)
    circular = min(gap, 30 - gap)
    assert circular >= 15
    assert same_cycle_start_collisions(schedules) == []


def test_group_five_220min_never_realign():
    requests = [
        (1, 220, 2048),
        (2, 220, 2048),
        (3, 220, 200),
        (4, 220, 20),
        (5, 220, 800),
    ]
    schedules = assign_many(requests)
    _print_group("G3 五条 220min 大小网段混部", schedules)
    assert all(item.cycle_minutes == 220 for item in schedules)
    assert all(0 <= item.offset_minutes < 220 for item in schedules)
    assert same_cycle_start_collisions(schedules) == []
    horizon = 220 * 3
    collisions = exact_start_collisions(schedules, horizon_minutes=horizon)
    assert collisions == []
    first, second = schedules[0], schedules[1]
    gap = abs(first.offset_minutes - second.offset_minutes)
    circular = min(gap, 220 - gap)
    assert circular >= 90


def test_group_220_avoids_dense_30min_cluster():
    thirty = assign_many([(index, 30, 20) for index in range(1, 9)])
    large = assign_offset(task_id=100, cycle_minutes=220, target_count=2048, existing=thirty)
    schedules = [*thirty, large]
    _print_group("G4 先 8 条 30min 小任务，再建 1 条 220min /21", schedules)
    thirty_starts = {start for item in thirty for start in fire_starts(item.offset_minutes, item.cycle_minutes, 660)}
    large_starts = fire_starts(large.offset_minutes, large.cycle_minutes, 660)
    exact_hits = [start for start in large_starts if start in thirty_starts]
    print(f"G4 220min fires={large_starts} exact_hits_with_30min={exact_hits}")
    assert exact_hits == []


def test_group_mixed_30_and_220_periodic_approach():
    requests = [
        *[(index, 30, 20) for index in range(1, 5)],
        *[(index, 220, 2048) for index in range(11, 14)],
    ]
    schedules = assign_many(requests)
    _print_group("G5 4条30min小 + 3条220min大（拍频 660min）", schedules)
    assert same_cycle_start_collisions(schedules) == []
    horizon = 660
    collisions = exact_start_collisions(schedules, horizon_minutes=horizon)
    print(f"G5 cross-cycle exact start collisions in 660min: {collisions}")
    near = []
    large = [item for item in schedules if item.cycle_minutes == 220]
    small = [item for item in schedules if item.cycle_minutes == 30]
    for big in large:
        for start in fire_starts(big.offset_minutes, big.cycle_minutes, horizon):
            for little in small:
                for other in fire_starts(little.offset_minutes, little.cycle_minutes, horizon):
                    gap = abs(start - other)
                    if 0 < gap <= 5:
                        near.append((start, big.task_id, other, little.task_id, gap))
    print(f"G5 220 与 30 启动相差≤5分钟: {near[:20] or '[]'}")
    assert collisions == []


def test_group_more_than_cycle_slots_still_unique_starts():
    schedules = assign_many([(index, 30, 20) for index in range(1, 16)])
    _print_group("G6 15条 30min 小任务（30 个整数分钟相位内应错开启动）", schedules)
    assert len({item.offset_minutes for item in schedules}) == 15
    assert same_cycle_start_collisions(schedules) == []


def _place_labeled(requests: list[tuple[int, int, int, str]]) -> list[tuple[str, CollectionSchedule]]:
    placed: list[CollectionSchedule] = []
    labeled: list[tuple[str, CollectionSchedule]] = []
    for task_id, cycle_minutes, target_count, label in requests:
        item = assign_offset(
            task_id=task_id,
            cycle_minutes=cycle_minutes,
            target_count=target_count,
            existing=placed,
        )
        placed.append(item)
        labeled.append((label, item))
    return labeled


def _circular_gap(left: int, right: int, cycle: int) -> int:
    gap = abs(left - right) % cycle
    return min(gap, cycle - gap)


def _print_labeled_group(title: str, rows: list[tuple[str, CollectionSchedule]]) -> None:
    schedules = [item for _label, item in rows]
    horizon = planning_horizon_minutes([item.cycle_minutes for item in schedules])
    collisions = exact_start_collisions(schedules, horizon_minutes=horizon)
    print(f"\n======== {title} ========")
    print(f"{'role':<22} {'cycle':>7} {'targets':>8} {'width':>6} " f"{'offset_min':>11} {'offset_sec':>11}  fires")
    for label, item in rows:
        fires = fire_starts(item.offset_minutes, item.cycle_minutes, min(horizon, max(item.cycle_minutes * 3, 750)))
        fire_text = ",".join(str(minute) for minute in fires[:6])
        if len(fires) > 6:
            fire_text += ",..."
        print(
            f"{label:<22} {item.cycle_minutes:>7} {item.target_count:>8} "
            f"{item.width_minutes:>6} {item.offset_minutes:>11} "
            f"{item.collection_offset_seconds:>11}  {fire_text}"
        )
    print(f"planning_horizon_minutes={horizon}")
    print(f"exact_start_collisions={collisions[:15] or '[]'}")
    if len(collisions) > 15:
        print(f"  ... total {len(collisions)} collision minutes")
    print(f"same_cycle_same_offset={same_cycle_start_collisions(schedules) or '[]'}")
    devices = [(label, item) for label, item in rows if label.endswith("device")]
    if len(devices) >= 2:
        print("250min device pairwise circular gap:")
        for index, (left_label, left) in enumerate(devices):
            for right_label, right in devices[index + 1 :]:
                gap = _circular_gap(left.offset_minutes, right.offset_minutes, left.cycle_minutes)
                print(f"  {left_label} vs {right_label}: {gap}min")
    pairs = list(zip([row for row in rows if row[0].endswith("device")], [row for row in rows if row[0].endswith("topo")]))
    if pairs:
        print("same-subnet device vs topo:")
        for (device_label, device), (topo_label, topo) in pairs:
            if device.cycle_minutes == topo.cycle_minutes:
                gap = _circular_gap(device.offset_minutes, topo.offset_minutes, device.cycle_minutes)
                print(f"  {device_label} vs {topo_label}: circular {gap}min (same cycle)")
            else:
                print(
                    f"  {device_label} offset={device.offset_minutes} / {topo_label} "
                    f"offset={topo.offset_minutes} (cycles {device.cycle_minutes}/{topo.cycle_minutes})"
                )


def test_group_large_network_host_topology_250min():
    """主机 + 1000+ 网段设备/拓扑。设备 250min；拓扑走推荐 5 倍=1250min。"""
    rows = _place_labeled(
        [
            (1, 30, 80, "host-office"),
            (2, 30, 150, "host-dc"),
            (3, 30, 40, "host-core"),
            (11, 250, 1200, "net-A-device"),
            (12, 1250, 1200, "net-A-topo"),
            (21, 250, 1600, "net-B-device"),
            (22, 1250, 1600, "net-B-topo"),
            (31, 250, 2048, "net-C-device"),
            (32, 1250, 2048, "net-C-topo"),
            (41, 250, 1100, "net-D-device"),
            (42, 1250, 1100, "net-D-topo"),
        ]
    )
    _print_labeled_group(
        "G7 主机30min + 4个1000+网段 设备250min / 拓扑1250min",
        rows,
    )
    devices = [item for label, item in rows if label.endswith("device")]
    topos = [item for label, item in rows if label.endswith("topo")]
    assert [item.cycle_minutes for item in devices] == [250, 250, 250, 250]
    assert len({item.offset_minutes for item in devices}) == 4
    assert len({item.offset_minutes for item in topos}) == 4
    assert same_cycle_start_collisions([item for _label, item in rows]) == []
    gaps = [_circular_gap(left.offset_minutes, right.offset_minutes, 250) for index, left in enumerate(devices) for right in devices[index + 1 :]]
    assert min(gaps) >= 20


def test_group_large_network_device_and_topo_same_250min():
    """设备和拓扑都设成 250min：同一网段两枪必须错开，多个 1000+ 网段也要错开。"""
    rows = _place_labeled(
        [
            (1, 30, 80, "host-office"),
            (2, 30, 150, "host-dc"),
            (11, 250, 1200, "net-A-device"),
            (12, 250, 1200, "net-A-topo"),
            (21, 250, 1600, "net-B-device"),
            (22, 250, 1600, "net-B-topo"),
            (31, 250, 2048, "net-C-device"),
            (32, 250, 2048, "net-C-topo"),
            (41, 250, 1100, "net-D-device"),
            (42, 250, 1100, "net-D-topo"),
        ]
    )
    _print_labeled_group(
        "G8 主机30min + 4个1000+网段 设备与拓扑都是250min",
        rows,
    )
    schedules = [item for _label, item in rows]
    assert same_cycle_start_collisions(schedules) == []
    horizon = planning_horizon_minutes([item.cycle_minutes for item in schedules])
    assert exact_start_collisions(schedules, horizon_minutes=horizon) == []
    devices = [item for label, item in rows if label.endswith("device")]
    topos = [item for label, item in rows if label.endswith("topo")]
    assert len({item.offset_minutes for item in devices + topos}) == 8
    for device, topo in zip(devices, topos):
        assert _circular_gap(device.offset_minutes, topo.offset_minutes, 250) >= 20
    device_gaps = [
        _circular_gap(left.offset_minutes, right.offset_minutes, 250) for index, left in enumerate(devices) for right in devices[index + 1 :]
    ]
    assert min(device_gaps) >= 20
