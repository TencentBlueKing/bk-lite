from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.log.models import CollectInstance, CollectInstanceOrganization, CollectType, LogExtractor, SystemVectorConfigState
from apps.log.services.log_extractor.rules import create_rule, create_type_rule, delete_rule, load_samples, load_type_samples, reorder_rules, reorder_type_rules, update_rule
from apps.log.views.collect_config import CollectInstanceViewSet


@pytest.fixture
def rule_instance(db):
    collect_type = CollectType.objects.create(name="rule-file", collector="Vector", icon="", attrs=[])
    instance = CollectInstance.objects.create(id="rule-instance", name="instance", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance=instance, organization=1)
    return instance


def _draft(name):
    return {
        "name": name,
        "extractor_type": "copy",
        "source_field": "message",
        "target_field": f"parsed.{name}",
        "condition": {"mode": "AND", "conditions": []},
        "config": {},
        "delete_source": False,
    }


@pytest.mark.unit
def test_samples_restore_victoria_logs_dotted_fields_to_runtime_shape(mocker):
    mocker.patch(
        "apps.log.services.log_extractor.rules.SearchService.search_logs",
        return_value=[
            {
                "instance_id": "packetbeat-instance",
                "network.community_id": "1:abc",
                "event.dataset": "flow",
            }
        ],
    )

    samples = load_samples(SimpleNamespace(pk="packetbeat-instance"), 10)

    assert samples == [
        {
            "instance_id": "packetbeat-instance",
            "network": {"community_id": "1:abc"},
            "event": {"dataset": "flow"},
        }
    ]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_rule_mutations_and_full_reorder_each_increment_one_generation(rule_instance, mocker):
    task = mocker.patch("apps.log.services.log_extractor.publication._publication_task")
    actor = SimpleNamespace(username="alice", domain="default")

    first, generation = create_rule(rule_instance, _draft("first"), actor)
    assert generation == 1
    first, generation = update_rule(first, {"name": "renamed"}, actor)
    assert generation == 2
    second, generation = create_rule(rule_instance, _draft("second"), actor)
    assert generation == 3
    generation = reorder_rules(rule_instance, [second.id, first.id])
    assert generation == 4
    generation = delete_rule(second)
    assert generation == 5

    assert list(LogExtractor.objects.values_list("id", "sort_order")) == [(first.id, 0)]
    assert SystemVectorConfigState.objects.get().desired_generation == 5
    assert task.return_value.delay.call_count == 5


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_instance_rule_limit_is_enforced_without_dirty_generation(rule_instance):
    LogExtractor.objects.bulk_create(
        [LogExtractor(collect_instance=rule_instance, sort_order=index, **_draft(f"rule{index}")) for index in range(20)]
    )

    with pytest.raises(ValidationError, match="最多 20 条"):
        create_rule(rule_instance, _draft("overflow"), SimpleNamespace(username="alice", domain="default"))

    assert not SystemVectorConfigState.objects.exists()


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_mysql_extractor_portable_constraints_reject_raw_queryset_duplicate(rule_instance):
    from django.db import IntegrityError, connection, models, transaction

    if connection.vendor != "mysql":
        pytest.skip("MySQL 5.7 legacy data migration contract")

    LogExtractor.objects.create(collect_instance=rule_instance, sort_order=0, **_draft("same"))
    duplicate = LogExtractor(collect_instance=rule_instance, sort_order=0, **_draft("same"))
    with pytest.raises(IntegrityError), transaction.atomic():
        models.QuerySet(model=LogExtractor, using="default").bulk_create([duplicate])


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_deleting_instance_with_multiple_rules_marks_one_generation(rule_instance, mocker):
    LogExtractor.objects.create(collect_instance=rule_instance, sort_order=0, **_draft("first"))
    LogExtractor.objects.create(collect_instance=rule_instance, sort_order=1, **_draft("second"))
    task = mocker.patch("apps.log.services.log_extractor.publication._publication_task")
    view = CollectInstanceViewSet()
    mocker.patch.object(view, "_authorize_instances", return_value=([rule_instance], None))

    response = view.remove_collect_instance(SimpleNamespace(data={"instance_ids": [rule_instance.id]}))

    assert response.status_code == 200
    assert not CollectInstance.objects.filter(pk=rule_instance.pk).exists()
    assert not LogExtractor.objects.exists()
    assert SystemVectorConfigState.objects.get().desired_generation == 1
    task.return_value.delay.assert_called_once_with(1)


@pytest.fixture
def syslog_type(db):
    return CollectType.objects.create(name="syslog", collector="Vector", icon="", attrs=[])


@pytest.mark.unit
def test_type_samples_query_collect_type_not_instance_id(mocker, syslog_type):
    search = mocker.patch(
        "apps.log.services.log_extractor.rules.SearchService.search_logs",
        return_value=[{"collect_type": "syslog", "message": "kernel: oops"}],
    )

    samples = load_type_samples(syslog_type, 10)

    assert samples == [{"collect_type": "syslog", "message": "kernel: oops"}]
    assert search.call_args.args[0] == 'collect_type:"syslog"'


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_type_rule_mutations_increment_one_generation_and_stay_instance_free(syslog_type, mocker):
    task = mocker.patch("apps.log.services.log_extractor.publication._publication_task")
    actor = SimpleNamespace(username="alice", domain="default")

    first, generation = create_type_rule(syslog_type, _draft("first"), actor)
    assert generation == 1
    assert first.collect_instance_id is None
    assert first.collect_type_id == syslog_type.id
    second, generation = create_type_rule(syslog_type, _draft("second"), actor)
    assert generation == 2
    generation = reorder_type_rules(syslog_type, [second.id, first.id])
    assert generation == 3
    generation = delete_rule(second)
    assert generation == 4

    remaining = LogExtractor.objects.get()
    assert remaining.pk == first.pk
    assert remaining.sort_order == 0
    assert remaining.collect_instance_id is None
    assert SystemVectorConfigState.objects.get().desired_generation == 4
    assert task.return_value.delay.call_count == 4


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_type_rule_limit_is_enforced_without_dirty_generation(syslog_type):
    LogExtractor.objects.bulk_create(
        [
            LogExtractor(collect_type=syslog_type, collect_instance=None, sort_order=index, **_draft(f"rule{index}"))
            for index in range(20)
        ]
    )

    with pytest.raises(ValidationError, match="最多 20 条"):
        create_type_rule(syslog_type, _draft("overflow"), SimpleNamespace(username="alice", domain="default"))

    assert not SystemVectorConfigState.objects.exists()
