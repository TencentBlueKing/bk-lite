"""采集任务启动相位（collection_offset）纯计算。

周期仍是「多久采一次」；本模块只在 [0, cycle) 上分配不同起步点。
无 DB / IO，可单测。
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass

OCCUPANCY_SLOT_MINUTES = 5
# 仅供测试/诊断枚举，生产分配不使用规划窗。
PLANNING_HORIZON_CAP_MINUTES = 7 * 24 * 60
# 不超过该长度时逐个相位评分，保证既有小周期结果不变。
_FULL_PHASE_SCAN_LIMIT = 4096


@dataclass(frozen=True)
class CollectionSchedule:
    task_id: int
    cycle_minutes: int
    target_count: int
    offset_minutes: int
    width_minutes: int

    @property
    def interval_seconds(self) -> int:
        return self.cycle_minutes * 60

    @property
    def collection_offset_seconds(self) -> int:
        return self.offset_minutes * 60


def occupancy_width_minutes(target_count: int, cycle_minutes: int) -> int:
    """按目标规模给出忙时宽度（分钟），不以周期裁剪实际估计负载。"""
    count = max(0, int(target_count))
    if count <= 64:
        slots = 1
    elif count <= 255:
        slots = 2
    elif count <= 1024:
        slots = 3
    else:
        slots = 4
    return slots * OCCUPANCY_SLOT_MINUTES


def planning_horizon_minutes(cycles: list[int], *, cap: int = PLANNING_HORIZON_CAP_MINUTES) -> int:
    """规划窗：各周期 LCM，超出上限则截断，至少覆盖两轮最长周期。"""
    positive = [max(1, int(cycle)) for cycle in cycles if int(cycle) > 0]
    if not positive:
        return 1
    horizon = 1
    for cycle in positive:
        horizon = math.lcm(horizon, cycle)
        if horizon > cap:
            horizon = cap
            break
    return max(horizon, min(cap, max(positive) * 2))


def fire_starts(offset_minutes: int, cycle_minutes: int, horizon_minutes: int) -> list[int]:
    cycle = max(1, int(cycle_minutes))
    offset = int(offset_minutes) % cycle
    horizon = max(1, int(horizon_minutes))
    return list(range(offset, horizon, cycle))


def _window_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def _circular_midpoints(positions: set[int], modulus: int) -> set[int]:
    """相邻占位之间的整数弧中点。奇数弧长保留两个同样最大的间距点。"""
    if modulus <= 0 or not positions:
        return set()
    ordered = sorted({position % modulus for position in positions})
    bounds = ordered + [ordered[0] + modulus]
    midpoints = set()
    for start, end in zip(bounds, bounds[1:]):
        span = end - start
        if span <= 0:
            continue
        midpoints.add((start + span // 2) % modulus)
        if span % 2:
            midpoints.add((start + span // 2 + 1) % modulus)
    return midpoints


def _overlap_offsets(previous: int, new_tail: int, old_tail: int, common: int) -> set[int]:
    """重叠窗口内的整数分钟、刚离开重叠的外缘，以及精确碰撞点。

    窗口宽度由忙时尾数决定。多个公约数叠在一起时，最低重叠会落在外缘，
    而不是落在另一个圆周的弧中点上。
    """
    if common <= 0:
        return set()
    base = previous % common
    positions = {base}
    if new_tail <= 0 or old_tail <= 0:
        return positions
    shift = 0
    forward_limit = new_tail if new_tail < common else common
    while shift < forward_limit:
        positions.add((base - shift) % common)
        shift += 1
    if new_tail < common:
        positions.add((base - new_tail) % common)
    back = 1
    backward_limit = old_tail if old_tail < common else common
    while back < backward_limit:
        positions.add((base - (common - back)) % common)
        back += 1
    if old_tail < common:
        positions.add((base - (common - old_tail)) % common)
    return positions


def _large_phase_residues(pairs, phase_period: int, preferred: int | None) -> list[int]:
    """超长相位的候选：重叠窗口及其外缘、各公约数弧中点、叠合空弧中点和首选偏移。

    各公约数上的点按该公约数平移到整个 phase_period。公约数 1 的间距是常数，不展开。
    不同公约数的占位还要在相位圆周上取相邻空弧的中点；只取各自圆周的中点会漏掉
    夹在两条公约数之间的最大空隙。
    平移结果是评分循环的 residue，不是最终分钟偏移。评分循环再换回
    offset = (seed + (residue - seed) % phase_period) % cycle；
    phase_period 等于周期时 residue 就是 offset。小于周期时同样先取 residue。
    """
    residues = set()
    occupied: dict[int, set[int]] = {}
    local_points: dict[int, set[int]] = {}
    replicas: set[int] = set()
    for (common, _repeats, previous, new_tail, old_tail, _constant), _count in pairs.items():
        occupied.setdefault(common, set()).add(previous % common)
        local_points.setdefault(common, set()).update(
            _overlap_offsets(previous, new_tail, old_tail, common)
        )
        if common <= 1:
            continue
        position = previous % common
        while position < phase_period:
            replicas.add(position)
            position += common
    for common, positions in occupied.items():
        local_points.setdefault(common, set()).update(_circular_midpoints(positions, common))
    for common, points in local_points.items():
        for point in points:
            if common <= 1:
                residues.add(point % phase_period)
                continue
            position = point % common
            while position < phase_period:
                residues.add(position)
                position += common
    residues.update(_circular_midpoints(replicas, phase_period))
    if preferred is not None:
        residues.add(preferred % phase_period)
    if not residues:
        residues.add(0)
    return [residue for residue in residues if 0 <= residue < phase_period]


def assign_offset(
    *,
    task_id: int,
    cycle_minutes: int,
    target_count: int,
    existing: list[CollectionSchedule] | None = None,
    preferred_offset_minutes: int | None = None,
    channel: str = "device",
) -> CollectionSchedule:
    """按长期碰撞频率、平均忙时重叠、最小间距分配；不枚举触发时间窗。"""
    cycle = max(1, int(cycle_minutes))
    width = occupancy_width_minutes(target_count, cycle)
    occupants = list(existing or [])
    preferred = preferred_offset_minutes
    if preferred is not None and not 0 <= preferred < cycle:
        preferred = None
    best_offset = preferred if preferred is not None else 0
    pairs = []
    for item in occupants:
        common = math.gcd(cycle, item.cycle_minutes)
        repeats = math.lcm(cycle, item.cycle_minutes)
        new_full, new_tail = divmod(width, common)
        old_full, old_tail = divmod(item.width_minutes, common)
        constant_overlap = new_full * old_full * common + new_full * old_tail + old_full * new_tail
        pairs.append((common, repeats, item.offset_minutes, new_tail, old_tail, constant_overlap))
    if pairs:
        # 同周期/相位/忙时的通道合并计数；大量存量 offset=0 时避免重复评分。
        pairs = Counter(pairs)
        # 评分只依赖 offset % gcd。相位不超过 4096 时逐分钟枚举，保持原结果。
        # 更长相位评重叠窗口及其外缘、各公约数弧中点，以及不同公约数叠合后的空弧中点。
        # 公约数 1 不展开。相同超长周期的评分次数不随分钟数增长，比较顺序不变。
        phase_period = math.lcm(*(pair[0] for pair in pairs))
        seed = int.from_bytes(hashlib.sha256(f"{task_id}:{channel}".encode()).digest()[:8], "big") % cycle
        best = None
        if phase_period <= _FULL_PHASE_SCAN_LIMIT:
            residues = range(phase_period)
        else:
            residues = _large_phase_residues(pairs, phase_period, preferred)
        for residue in residues:
            if preferred is not None and preferred % phase_period == residue:
                offset = preferred
            else:
                offset = (seed + (residue - seed) % phase_period) % cycle
            collisions = []
            overlaps = []
            gaps = []
            for (common, repeats, previous, new_tail, old_tail, constant), count in pairs.items():
                shift = (previous - offset) % common
                collisions.append(count / repeats if shift == 0 else 0)
                overlap = _window_overlap(0, new_tail, shift, shift + old_tail)
                overlap += _window_overlap(0, new_tail, shift - common, shift - common + old_tail)
                overlaps.append(count * (constant + overlap) / repeats)
                gaps.extend([min(shift, common - shift)] * count)
            score = (math.fsum(collisions), math.fsum(overlaps), tuple(-gap for gap in sorted(gaps)), offset != preferred, (offset - seed) % cycle)
            if best is None or score < best:
                best, best_offset = score, offset
    return CollectionSchedule(
        task_id=int(task_id),
        cycle_minutes=cycle,
        target_count=int(target_count),
        offset_minutes=best_offset,
        width_minutes=width,
    )


def assign_many(requests: list[tuple[int, int, int]]) -> list[CollectionSchedule]:
    """按顺序分配。(task_id, cycle_minutes, target_count)"""
    placed: list[CollectionSchedule] = []
    for task_id, cycle_minutes, target_count in requests:
        placed.append(
            assign_offset(
                task_id=task_id,
                cycle_minutes=cycle_minutes,
                target_count=target_count,
                existing=placed,
            )
        )
    return placed


def exact_start_collisions(
    schedules: list[CollectionSchedule],
    *,
    horizon_minutes: int | None = None,
) -> list[tuple[int, list[int]]]:
    """同一时刻有多个任务启动：(minute, [task_id...])。"""
    if not schedules:
        return []
    horizon = horizon_minutes or planning_horizon_minutes([item.cycle_minutes for item in schedules])
    by_time: dict[int, list[int]] = {}
    for item in schedules:
        for start in fire_starts(item.offset_minutes, item.cycle_minutes, horizon):
            by_time.setdefault(start, []).append(item.task_id)
    return [(minute, ids) for minute, ids in sorted(by_time.items()) if len(ids) > 1]


def same_cycle_start_collisions(schedules: list[CollectionSchedule]) -> list[tuple[int, int, int]]:
    """同周期、同偏移：稳态下每次都会撞。(cycle, offset, count)"""
    buckets: dict[tuple[int, int], list[int]] = {}
    for item in schedules:
        buckets.setdefault((item.cycle_minutes, item.offset_minutes), []).append(item.task_id)
    return [(cycle, offset, len(ids)) for (cycle, offset), ids in sorted(buckets.items()) if len(ids) > 1]
