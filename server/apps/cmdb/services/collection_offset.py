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
        # 所有评分只依赖 offset % gcd。等价候选折叠后仍覆盖每个整数分钟相位的评分，非采样。
        phase_period = math.lcm(*(pair[0] for pair in pairs))
        seed = int.from_bytes(hashlib.sha256(f"{task_id}:{channel}".encode()).digest()[:8], "big") % cycle
        best = None
        for residue in range(phase_period):
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
