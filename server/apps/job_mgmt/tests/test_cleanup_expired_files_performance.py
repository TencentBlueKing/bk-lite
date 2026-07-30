from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.job_mgmt import tasks
from apps.job_mgmt.models import DistributionFile
from apps.job_mgmt.tasks import cleanup_expired_distribution_files_task

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_batches_remote_cleanup_and_database_delete_while_preserving_failures():
    """批量清理复用一次异步边界、一次 DELETE，并保留远端失败记录。"""
    expired_rows = [
        DistributionFile.objects.create(
            original_name=f"{index}.rpm",
            file_key=file_key,
            team=team,
            expire_at=timezone.now() - timedelta(minutes=1),
        )
        for index, (file_key, team) in enumerate((("duplicate", 1), ("duplicate", 2), ("success", 2), ("failed", 1)))
    ]
    fresh = DistributionFile.objects.create(
        original_name="fresh.rpm",
        file_key="fresh",
        team=1,
        expire_at=timezone.now() + timedelta(days=1),
    )
    adapter_functions = []
    adapter_calls = []

    def fake_async_to_sync(async_function):
        adapter_functions.append(async_function)

        def invoke(file_keys, max_concurrency=None):
            adapter_calls.append((file_keys, max_concurrency))
            if isinstance(file_keys, list):
                return {
                    "duplicate": None,
                    "success": None,
                    "failed": RuntimeError("object store unavailable"),
                }
            return None

        return invoke

    with patch("apps.job_mgmt.tasks.async_to_sync", side_effect=fake_async_to_sync):
        with CaptureQueriesContext(connection) as queries:
            cleanup_expired_distribution_files_task()

    delete_count = sum(query["sql"].lstrip().upper().startswith("DELETE") for query in queries.captured_queries)
    assert (len(adapter_functions), delete_count) == (1, 1)
    assert len(adapter_calls) == 1
    assert adapter_calls[0][0] == ["failed", "success", "duplicate", "duplicate"]
    assert adapter_calls[0][1] > 0
    assert not DistributionFile.objects.filter(id__in=[row.id for row in expired_rows[:3]]).exists()
    assert DistributionFile.objects.filter(id=expired_rows[3].id).exists()
    assert DistributionFile.objects.filter(id=fresh.id).exists()


def test_limits_rows_and_delete_parameters_per_cleanup_batch(monkeypatch):
    for index in range(5):
        DistributionFile.objects.create(
            original_name=f"{index}.rpm",
            file_key=f"batch-{index}",
            team=index % 2 + 1,
            expire_at=timezone.now() - timedelta(minutes=1),
        )
    remote_batches = []

    def fake_async_to_sync(async_function):
        def invoke(file_keys, max_concurrency=None):
            remote_batches.append(file_keys)
            return {file_key: None for file_key in file_keys}

        return invoke

    monkeypatch.setattr(tasks, "DISTRIBUTION_FILE_CLEANUP_BATCH_SIZE", 2)
    with patch("apps.job_mgmt.tasks.async_to_sync", side_effect=fake_async_to_sync):
        with CaptureQueriesContext(connection) as queries:
            cleanup_expired_distribution_files_task()

    delete_count = sum(query["sql"].lstrip().upper().startswith("DELETE") for query in queries.captured_queries)
    assert [len(batch) for batch in remote_batches] == [2, 2, 1]
    assert delete_count == 3


def test_keeps_all_rows_when_batch_remote_bridge_fails():
    rows = [
        DistributionFile.objects.create(
            original_name=f"{index}.rpm",
            file_key=f"remote-failure-{index}",
            team=index + 1,
            expire_at=timezone.now() - timedelta(minutes=1),
        )
        for index in range(2)
    ]

    with patch("apps.job_mgmt.tasks.async_to_sync", side_effect=ConnectionError("NATS unavailable")):
        cleanup_expired_distribution_files_task()

    assert DistributionFile.objects.filter(id__in=[row.id for row in rows]).count() == 2


def test_keeps_all_remote_success_rows_when_database_batch_delete_fails():
    rows = [
        DistributionFile.objects.create(
            original_name=f"{index}.rpm",
            file_key=f"database-failure-{index}",
            team=index + 1,
            expire_at=timezone.now() - timedelta(minutes=1),
        )
        for index in range(2)
    ]

    def fake_async_to_sync(async_function):
        return lambda file_keys, **kwargs: {file_key: None for file_key in file_keys}

    with (
        patch("apps.job_mgmt.tasks.async_to_sync", side_effect=fake_async_to_sync),
        patch("django.db.models.query.QuerySet.delete", side_effect=RuntimeError("database unavailable")),
    ):
        cleanup_expired_distribution_files_task()

    assert DistributionFile.objects.filter(id__in=[row.id for row in rows]).count() == 2
