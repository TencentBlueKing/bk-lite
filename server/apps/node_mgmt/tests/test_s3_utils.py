import asyncio

import pytest
from nats.js.errors import ObjectNotFoundError

from apps.node_mgmt.utils import s3


@pytest.mark.unit
async def test_delete_s3_files_reuses_connection_bounds_concurrency_and_reports_each_key(monkeypatch):
    instances = []
    gather_widths = []
    original_gather = asyncio.gather

    class FakeJetStreamService:
        def __init__(self):
            self.active = 0
            self.peak_active = 0
            self.connect_count = 0
            self.close_count = 0
            self.deleted_keys = []
            instances.append(self)

        async def connect(self):
            self.connect_count += 1

        async def delete(self, key):
            self.active += 1
            self.peak_active = max(self.peak_active, self.active)
            self.deleted_keys.append(key)
            await asyncio.sleep(0)
            self.active -= 1
            if key == "missing":
                raise ObjectNotFoundError()
            if key == "failed":
                raise RuntimeError("object store unavailable")

        async def close(self):
            self.close_count += 1

    monkeypatch.setattr(s3, "JetStreamService", FakeJetStreamService)

    async def tracking_gather(*awaitables):
        gather_widths.append(len(awaitables))
        return await original_gather(*awaitables)

    monkeypatch.setattr(s3.asyncio, "gather", tracking_gather)

    results = await s3.delete_s3_files(
        ["first", "missing", "first", "failed"],
        max_concurrency=2,
    )

    assert len(instances) == 1
    instance = instances[0]
    assert (instance.connect_count, instance.close_count) == (1, 1)
    assert instance.deleted_keys == ["first", "missing", "failed"]
    assert instance.peak_active == 2
    assert gather_widths == [2]
    assert list(results) == ["first", "missing", "failed"]
    assert results["first"] is None
    assert results["missing"] is None
    assert isinstance(results["failed"], RuntimeError)


@pytest.mark.unit
async def test_delete_s3_files_closes_partially_initialized_connection(monkeypatch):
    instances = []

    class FailingJetStreamService:
        def __init__(self):
            self.nc = None
            self.close_count = 0
            instances.append(self)

        async def connect(self):
            self.nc = object()
            raise RuntimeError("object store initialization failed")

        async def close(self):
            self.close_count += 1

    monkeypatch.setattr(s3, "JetStreamService", FailingJetStreamService)

    with pytest.raises(RuntimeError, match="object store initialization failed"):
        await s3.delete_s3_files(["first"], max_concurrency=1)

    assert instances[0].close_count == 1
