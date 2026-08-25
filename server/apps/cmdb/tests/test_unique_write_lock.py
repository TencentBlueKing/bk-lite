import threading
from datetime import timedelta

import pytest
from django.utils.timezone import now

from apps.cmdb.models.operation import CmdbUniqueWriteLock
from apps.cmdb.services.unique_write_lock import UniqueWriteLockService


@pytest.mark.django_db
def test_same_unique_signature_has_single_owner_and_stale_takeover():
    assert UniqueWriteLockService.acquire("host:r1:abc", owner_token="owner-1", lease_seconds=60) is True
    assert UniqueWriteLockService.acquire("host:r1:abc", owner_token="owner-2", lease_seconds=60) is False

    CmdbUniqueWriteLock.objects.filter(lock_key="host:r1:abc").update(
        lease_expires_at=now() - timedelta(seconds=1)
    )
    assert UniqueWriteLockService.acquire("host:r1:abc", owner_token="owner-2", lease_seconds=60) is True
    assert UniqueWriteLockService.release("host:r1:abc", owner_token="owner-1") is False
    assert UniqueWriteLockService.release("host:r1:abc", owner_token="owner-2") is True


@pytest.mark.django_db
def test_lock_keys_are_stable_and_ignore_empty_unique_values():
    check_attr_map = {
        "is_only": {"serial": "序列号"},
        "unique_rules": [type("Rule", (), {"rule_id": "r1", "field_ids": ["region", "name"]})()],
    }

    keys = UniqueWriteLockService.build_lock_keys(
        "host", {"serial": "S-1", "region": "cn", "name": "api"}, check_attr_map
    )
    assert len(keys) == 2
    assert keys == UniqueWriteLockService.build_lock_keys(
        "host", {"name": "api", "region": "cn", "serial": "S-1"}, check_attr_map
    )
    assert UniqueWriteLockService.build_lock_keys(
        "host", {"serial": "", "region": "cn", "name": ""}, check_attr_map
    ) == []


@pytest.mark.django_db(transaction=True)
def test_serialize_fails_fast_on_contention_and_succeeds_after_holder_exits():
    entered = []
    first_entered = threading.Event()
    release_first = threading.Event()
    second_finished = threading.Event()

    def _run_first():
        with UniqueWriteLockService.serialize("display-sync-order"):
            entered.append("first")
            first_entered.set()
            assert release_first.wait(timeout=5)

    def _run_contender():
        with pytest.raises(TimeoutError, match="CMDB 写锁正被占用"):
            with UniqueWriteLockService.serialize("display-sync-order"):
                entered.append("unexpected")
        second_finished.set()

    first = threading.Thread(target=_run_first)
    second = threading.Thread(target=_run_contender)
    first.start()
    assert first_entered.wait(timeout=5)
    second.start()
    assert second_finished.wait(timeout=2)
    assert entered == ["first"]
    release_first.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    with UniqueWriteLockService.serialize("display-sync-order"):
        entered.append("retry")
    assert entered == ["first", "retry"]
