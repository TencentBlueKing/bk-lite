"""相位分配契约：独立时间枚举校验长期评分。"""
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
