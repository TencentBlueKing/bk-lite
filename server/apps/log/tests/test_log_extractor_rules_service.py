from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.log.models import CollectInstance, CollectInstanceOrganization, CollectType, LogExtractor, SystemVectorConfigState
from apps.log.services.log_extractor.rules import create_rule, delete_rule, reorder_rules, update_rule
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
