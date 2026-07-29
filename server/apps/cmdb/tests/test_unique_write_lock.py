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
