import pytest

from apps.operation_analysis.management.commands.audit_directory_cycles import find_directory_cycles

pytestmark = pytest.mark.unit


def test_find_directory_cycles_reports_each_cycle_once():
    parent_by_id = {
        1: 2,
        2: 1,
        3: 2,
        4: None,
        5: 6,
        6: 7,
        7: 5,
    }

    assert find_directory_cycles(parent_by_id) == [(1, 2), (5, 6, 7)]


def test_find_directory_cycles_accepts_acyclic_and_missing_parents():
    assert find_directory_cycles({1: None, 2: 1, 3: 99}) == []
