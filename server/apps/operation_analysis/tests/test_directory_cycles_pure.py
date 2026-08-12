import signal
from contextlib import contextmanager

import pytest
from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.operation_analysis.models.models import Directory
from apps.operation_analysis.serializers.directory_serializers import DashboardModelSerializer, DirectoryModelSerializer

pytestmark = pytest.mark.unit


class _ParentWalkTimedOut(Exception):
    pass


@contextmanager
def _parent_walk_deadline(seconds=1):
    def _raise_timeout(_signum, _frame):
        raise _ParentWalkTimedOut("parent walk did not terminate")

    previous_handler = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _directory(pk, name, parent=None):
    return Directory(id=pk, name=name, groups=[1], parent=parent)


def test_directory_rejects_self_parent():
    directory = _directory(1, "self-parent")
    directory.parent = directory

    with _parent_walk_deadline(), pytest.raises(ValidationError, match="cannot contain cycles"):
        directory.clean()


def test_directory_rejects_reparenting_ancestor_to_descendant():
    persisted_root = _directory(1, "root")
    child = _directory(2, "child", parent=persisted_root)
    root = _directory(1, "root")
    root.parent = child

    with pytest.raises(ValidationError, match="cannot contain cycles"):
        root.clean()


def test_directory_get_level_rejects_historical_cycle():
    first = _directory(1, "first")
    second = _directory(2, "second", parent=first)
    first.parent = second

    with _parent_walk_deadline(), pytest.raises(ValidationError, match="cannot contain cycles"):
        first.get_level()


def test_directory_allows_valid_reparenting():
    second_root = _directory(2, "second-root")
    child = _directory(3, "child", parent=second_root)

    child.clean()

    assert child.parent == second_root
    assert child.get_level() == 1


def test_directory_serializer_returns_validation_error_for_cycle_parent():
    persisted_root = _directory(1, "root")
    child = _directory(2, "child", parent=persisted_root)
    serializer = object.__new__(DirectoryModelSerializer)
    serializer.instance = _directory(1, "root")

    with pytest.raises(DRFValidationError, match="cannot contain cycles"):
        serializer.validate_parent(child)


def test_canvas_serializer_rejects_historical_directory_cycle():
    first = _directory(1, "first")
    second = _directory(2, "second", parent=first)
    first.parent = second
    serializer = object.__new__(DashboardModelSerializer)
    serializer.instance = None

    with pytest.raises(DRFValidationError, match="cannot contain cycles"):
        serializer._validate_directory_chain_visibility({"directory": first, "groups": [1]})
