"""相位分配契约：独立时间枚举校验长期评分。"""
import hashlib
import math
from math import lcm
from random import Random

import pytest

from apps.cmdb.services.collection_offset import CollectionSchedule, assign_offset, occupancy_width_minutes

pytestmark = pytest.mark.unit


def test_busy_width_is_not_shortened_by_cycle():
    assert occupancy_width_minutes(2048, 30) == 20
    assert occupancy_width_minutes(20, 1) == 5


def test_assignment_uses_full_period_including_wrapped_busy_windows():
    rng = Random(17)
    for case in range(40):
        period = rng.randint(2, 12)
        other_period = rng.randint(2, 12)
        other = CollectionSchedule(1, other_period, 20, rng.randrange(other_period), 5)
        horizon = lcm(period, other_period)
        scores = []
        for offset in range(period):
            starts = [t for t in range(horizon) if (t - offset) % period == 0]
            collisions = sum((t - other.offset_minutes) % other_period == 0 for t in starts)
            overlap = 0
            for t in range(horizon):
                new_busy = sum((t - offset - age) % period == 0 for age in range(5))
                old_busy = sum((t - other.offset_minutes - age) % other_period == 0 for age in range(5))
                overlap += new_busy * old_busy
            other_starts = [t for t in range(horizon) if (t - other.offset_minutes) % other_period == 0]
            gap = min(min(abs(a - b), horizon - abs(a - b)) for a in starts for b in other_starts)
            scores.append((collisions, overlap, -gap))
        chosen = assign_offset(task_id=case + 2, cycle_minutes=period, target_count=20, existing=[other])
        assert scores[chosen.offset_minutes] == min(scores)


def test_keep_previous_offset_when_equally_good():
    chosen = assign_offset(task_id=7, cycle_minutes=30, target_count=20, existing=[], preferred_offset_minutes=12)
    assert chosen.offset_minutes == 12


def test_coprime_periods_accept_unavoidable_collision():
    from apps.cmdb.services.collection_offset import exact_start_collisions

    existing = CollectionSchedule(1, 30, 20, 0, 5)
    chosen = assign_offset(task_id=2, cycle_minutes=31, target_count=20, existing=[existing])
    assert 0 <= chosen.offset_minutes < 31
    assert len(exact_start_collisions([existing, chosen], horizon_minutes=930)) == 1


def test_full_phase_capacity_still_returns_legal_deterministic_result():
    existing = [CollectionSchedule(i, 3, 20, i, 5) for i in range(3)]
    chosen = assign_offset(task_id=10, cycle_minutes=3, target_count=20, existing=existing)
    assert 0 <= chosen.offset_minutes < 3
    assert chosen == assign_offset(task_id=10, cycle_minutes=3, target_count=20, existing=list(reversed(existing)))


def test_large_coprime_cycle_uses_equivalent_phases_without_time_expansion():
    existing = [CollectionSchedule(1, 30, 20, 0, 5)]
    chosen = assign_offset(task_id=2, cycle_minutes=10**12 + 1, target_count=20, existing=existing)
    assert 0 <= chosen.offset_minutes < chosen.cycle_minutes


def _window_overlap(a_start, a_end, b_start, b_end):
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def _exhaustive_best_offset(task_id, cycle_minutes, existing, preferred_offset_minutes=None, channel="device"):
    """独立穷举每个相位。调用方不得把上亿分钟的周期传进来。"""
    cycle = max(1, int(cycle_minutes))
    width = occupancy_width_minutes(20, cycle)
    preferred = preferred_offset_minutes
    if preferred is not None and not 0 <= preferred < cycle:
        preferred = None
    pairs = []
    for item in existing:
        common = math.gcd(cycle, item.cycle_minutes)
        repeats = math.lcm(cycle, item.cycle_minutes)
        new_full, new_tail = divmod(width, common)
        old_full, old_tail = divmod(item.width_minutes, common)
        constant = new_full * old_full * common + new_full * old_tail + old_full * new_tail
        pairs.append((common, repeats, item.offset_minutes, new_tail, old_tail, constant, 1))
    phase_period = math.lcm(*(pair[0] for pair in pairs))
    seed = int.from_bytes(hashlib.sha256(f"{task_id}:{channel}".encode()).digest()[:8], "big") % cycle
    best = None
    best_offset = None
    for residue in range(phase_period):
        if preferred is not None and preferred % phase_period == residue:
            offset = preferred
        else:
            offset = (seed + (residue - seed) % phase_period) % cycle
        collisions = []
        overlaps = []
        gaps = []
        for common, repeats, previous, new_tail, old_tail, constant, count in pairs:
            shift = (previous - offset) % common
            collisions.append(count / repeats if shift == 0 else 0)
            overlap = _window_overlap(0, new_tail, shift, shift + old_tail)
            overlap += _window_overlap(0, new_tail, shift - common, shift - common + old_tail)
            overlaps.append(count * (constant + overlap) / repeats)
            gaps.extend([min(shift, common - shift)] * count)
        score = (
            math.fsum(collisions),
            math.fsum(overlaps),
            tuple(-gap for gap in sorted(gaps)),
            offset != preferred,
            (offset - seed) % cycle,
        )
        if best is None or score < best:
            best, best_offset = score, offset
    return best_offset


def _track_phase_ranges(monkeypatch):
    seen = []
    real_range = range

    def wrapped(*args):
        stop = args[0] if len(args) == 1 else args[1]
        seen.append(stop)
        if isinstance(stop, int) and stop > 4096:
            return real_range(0)
        return real_range(*args)

    monkeypatch.setattr("apps.cmdb.services.collection_offset.range", wrapped, raising=False)
    return seen


def test_same_long_cycle_matches_exhaustive_without_scanning_each_minute(monkeypatch):
    period = 20000
    seen = _track_phase_ranges(monkeypatch)
    existing = [CollectionSchedule(1, period, 20, 123, 5)]
    chosen = assign_offset(task_id=2, cycle_minutes=period, target_count=20, existing=existing)
    assert all(stop <= 4096 for stop in seen), seen
    assert chosen.offset_minutes == _exhaustive_best_offset(2, period, existing)
    assert chosen.offset_minutes == (123 + period // 2) % period

    crowded = [CollectionSchedule(index + 1, period, 20, offset, 5) for index, offset in enumerate((0, 250, 800))]
    seen.clear()
    chosen = assign_offset(task_id=9, cycle_minutes=period, target_count=20, existing=crowded)
    assert all(stop <= 4096 for stop in seen), seen
    assert chosen.offset_minutes == _exhaustive_best_offset(9, period, crowded)
    assert chosen.offset_minutes == 10400

    odd_period = 20001
    preferred = (123 + odd_period // 2 + 1) % odd_period
    odd_existing = [CollectionSchedule(1, odd_period, 20, 123, 5)]
    seen.clear()
    chosen = assign_offset(
        task_id=2,
        cycle_minutes=odd_period,
        target_count=20,
        existing=odd_existing,
        preferred_offset_minutes=preferred,
    )
    assert all(stop <= 4096 for stop in seen), seen
    assert chosen.offset_minutes == preferred
    assert chosen.offset_minutes == _exhaustive_best_offset(2, odd_period, odd_existing, preferred)


def test_hundred_million_minute_cycle_returns_opposite_midpoint(monkeypatch):
    period = 100_000_000
    seen = _track_phase_ranges(monkeypatch)
    existing_offset = 7
    chosen = assign_offset(
        task_id=2,
        cycle_minutes=period,
        target_count=20,
        existing=[CollectionSchedule(1, period, 20, existing_offset, 5)],
    )
    assert all(stop <= 4096 for stop in seen), seen
    assert chosen.offset_minutes == (existing_offset + period // 2) % period


def test_distinct_long_divisors_match_exhaustive_without_full_phase_scan(monkeypatch):
    existing = [
        CollectionSchedule(1, 15000, 20, 100, 5),
        CollectionSchedule(3, 12000, 20, 50, 5),
    ]
    seen = _track_phase_ranges(monkeypatch)
    expected = {20000: 18050, 40000: 38050}
    for period in (20000, 40000):
        seen.clear()
        chosen = assign_offset(task_id=2, cycle_minutes=period, target_count=20, existing=existing)
        assert all(stop <= 4096 for stop in seen), seen
        assert chosen.offset_minutes == expected[period]
        assert chosen.offset_minutes == _exhaustive_best_offset(2, period, existing)


def test_phase_period_up_to_4096_keeps_full_enumeration(monkeypatch):
    seen = _track_phase_ranges(monkeypatch)
    existing = [CollectionSchedule(1, 4096, 20, 10, 5)]
    chosen = assign_offset(task_id=2, cycle_minutes=4096, target_count=20, existing=existing)
    assert 4096 in seen
    assert chosen.offset_minutes == _exhaustive_best_offset(2, 4096, existing)

    seen.clear()
    odd_existing = [CollectionSchedule(1, 4097, 20, 10, 5)]
    chosen = assign_offset(task_id=2, cycle_minutes=4097, target_count=20, existing=odd_existing)
    assert all(stop <= 4096 for stop in seen), seen
    assert chosen.offset_minutes == _exhaustive_best_offset(2, 4097, odd_existing)


def test_stacked_divisors_match_exhaustive_when_phase_exceeds_scan_limit(monkeypatch):
    """多个公约数叠成超过 4096 的相位时，结果仍等于逐相位评分。

    相位小于周期时，residue 还要按 seed 换回 offset。调用方不得把上亿分钟交给穷举。
    """
    seen = _track_phase_ranges(monkeypatch)
    overlap_existing = [
        CollectionSchedule(1, 4, 20, 0, 5),
        CollectionSchedule(2, 12, 20, 6, 5),
        CollectionSchedule(3, 4200, 20, 0, 5),
    ]
    overlap_expected = {4200: 2099, 8400: 6299}
    for period in (4200, 8400):
        seen.clear()
        chosen = assign_offset(task_id=2, cycle_minutes=period, target_count=20, existing=overlap_existing)
        assert all(stop <= 4096 for stop in seen), seen
        assert chosen.offset_minutes == overlap_expected[period]
        assert chosen.offset_minutes == _exhaustive_best_offset(2, period, overlap_existing)

    midpoint_existing = [
        CollectionSchedule(1, 420, 20, 200, 5),
        CollectionSchedule(2, 420, 20, 80, 5),
        CollectionSchedule(3, 700, 20, 40, 5),
        CollectionSchedule(4, 700, 20, 520, 5),
        CollectionSchedule(5, 280, 20, 260, 5),
    ]
    midpoint_expected = {4200: 3740, 8400: 7940}
    for period in (4200, 8400):
        seen.clear()
        chosen = assign_offset(task_id=2, cycle_minutes=period, target_count=20, existing=midpoint_existing)
        assert all(stop <= 4096 for stop in seen), seen
        assert chosen.offset_minutes == midpoint_expected[period]
        assert chosen.offset_minutes == _exhaustive_best_offset(2, period, midpoint_existing)
