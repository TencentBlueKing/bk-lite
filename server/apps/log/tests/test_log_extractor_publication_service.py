from unittest.mock import Mock

import pytest
from django.db import transaction

from apps.log.models import SystemVectorConfigState
from apps.log.services.log_extractor.publication import ensure_initial_snapshot, mark_dirty, publish_generation


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_published_generation_exits_before_changing_status(mocker):
    state = SystemVectorConfigState.objects.create(
        desired_generation=5,
        published_generation=5,
        status=SystemVectorConfigState.Status.PUBLISHED,
        published_content="last-good",
        published_checksum="sha256:old",
    )
    compiler = mocker.patch("apps.log.services.log_extractor.publication.compile_system_vector_config")

    result = publish_generation(5)

    state.refresh_from_db()
    assert result == "already_published"
    assert state.status == SystemVectorConfigState.Status.PUBLISHED
    compiler.assert_not_called()


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_stale_generation_exits_without_changing_latest_status(mocker):
    state = SystemVectorConfigState.objects.create(
        desired_generation=4,
        published_generation=2,
        status=SystemVectorConfigState.Status.PENDING,
        published_content="last-good",
        published_checksum="sha256:old",
    )
    compiler = mocker.patch("apps.log.services.log_extractor.publication.compile_system_vector_config")

    result = publish_generation(3)

    state.refresh_from_db()
    assert result == "stale"
    assert state.status == SystemVectorConfigState.Status.PENDING
    assert state.published_generation == 2
    compiler.assert_not_called()


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_generation_failure_keeps_last_good_snapshot(mocker):
    state = SystemVectorConfigState.objects.create(
        desired_generation=2,
        published_generation=1,
        status=SystemVectorConfigState.Status.PENDING,
        published_content="last-good",
        published_checksum="sha256:old",
    )
    mocker.patch("apps.log.services.log_extractor.publication.compile_system_vector_config", side_effect=ValueError("broken rule"))

    result = publish_generation(2)

    state.refresh_from_db()
    assert result == "failed"
    assert state.status == SystemVectorConfigState.Status.FAILED
    assert state.published_content == "last-good"
    assert state.published_generation == 1
    assert "broken rule" not in state.last_error


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_on_commit_enqueue_failure_marks_saved_generation_failed(mocker):
    task = Mock()
    task.delay.side_effect = RuntimeError("broker secret must not leak")
    mocker.patch("apps.log.services.log_extractor.publication._publication_task", return_value=task)

    with transaction.atomic():
        generation = mark_dirty()

    state = SystemVectorConfigState.objects.get()
    assert generation == 1
    assert state.desired_generation == 1
    assert state.status == SystemVectorConfigState.Status.FAILED
    assert "broker secret" not in state.last_error


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_initial_snapshot_without_rules_is_complete_noop_config():
    snapshot = ensure_initial_snapshot()

    assert snapshot.generation == 1
    assert "server_nats:" in snapshot.content
    assert "log_extractors:" in snapshot.content
    assert "victoria_logs:" in snapshot.content
    assert "source: . = ." in snapshot.content
