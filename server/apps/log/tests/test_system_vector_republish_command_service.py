import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.log.models import CollectInstance, CollectType, LogExtractor, SystemVectorConfigState


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_republish_command_replaces_legacy_snapshot_with_complete_current_contract():
    SystemVectorConfigState.objects.create(
        desired_generation=4,
        published_generation=4,
        status=SystemVectorConfigState.Status.PUBLISHED,
        published_content="sources: {}\n",
        published_checksum="sha256:legacy",
    )
    stdout = io.StringIO()

    call_command("republish_system_vector_config", stdout=stdout)

    state = SystemVectorConfigState.objects.get()
    assert state.desired_generation == 5
    assert state.published_generation == 5
    assert state.status == SystemVectorConfigState.Status.PUBLISHED
    assert state.published_content.startswith("# bk-lite-system-vector-contract-version: 1\n")
    assert "normalize_event:" in state.published_content
    assert "log_extractors:" in state.published_content
    assert "prepare_victoria_logs:" in state.published_content
    assert "victoria_logs:" in state.published_content
    assert "generation=5" in stdout.getvalue()
    assert "contract_version=1" in stdout.getvalue()


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_republish_command_keeps_last_good_snapshot_when_complete_config_is_invalid():
    state = SystemVectorConfigState.objects.create(
        desired_generation=4,
        published_generation=4,
        status=SystemVectorConfigState.Status.PUBLISHED,
        published_content="last-good\n",
        published_checksum="sha256:last-good",
    )
    collect_type = CollectType.objects.create(name="syslog", collector="vector", icon="syslog")
    collect_instance = CollectInstance.objects.create(id="syslog-instance", name="syslog", collect_type=collect_type)
    LogExtractor.objects.create(
        name="invalid-system-field-write",
        collect_instance=collect_instance,
        condition={},
        extractor_type=LogExtractor.ExtractorType.COPY,
        source_field="message",
        target_field="collect_timestamp",
        config={},
        sort_order=0,
    )

    with pytest.raises(CommandError, match="系统 Vector 配置重新发布失败"):
        call_command("republish_system_vector_config")

    state.refresh_from_db()
    assert state.desired_generation == 5
    assert state.published_generation == 4
    assert state.status == SystemVectorConfigState.Status.FAILED
    assert state.published_content == "last-good\n"
    assert state.published_checksum == "sha256:last-good"
    assert "collect_timestamp" not in state.last_error
