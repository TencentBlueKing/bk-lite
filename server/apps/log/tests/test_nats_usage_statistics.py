from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from types import SimpleNamespace

import pytest

from apps.log.models.collect_type import CollectType
from apps.log.models.extractor import LogExtractor
from apps.log.models.instance import CollectInstance, CollectInstanceOrganization
from apps.log.models.policy import Alert, Policy, PolicyOrganization
from apps.log.nats import log as log_nats

pytestmark = pytest.mark.django_db


def _user_info(team=1):
    return {
        "user": SimpleNamespace(username="alice", domain="domain.com"),
        "domain": "domain.com",
        "team": team,
        "include_children": False,
    }


def _grant(mocker, team=1):
    mocker.patch("apps.log.nats.log.get_permission_rules", return_value={"team": [team]})


def test_log_usage_statistics_counts_org_instances_and_bound_rate(mocker):
    _grant(mocker)
    collect_type = CollectType.objects.create(name="file", collector="Vector", icon="")
    bound = CollectInstance.objects.create(id="log-bound", name="bound", collect_type=collect_type, node_id="node-1")
    unbound = CollectInstance.objects.create(id="log-unbound", name="unbound", collect_type=collect_type, node_id="")
    foreign = CollectInstance.objects.create(id="log-foreign", name="foreign", collect_type=collect_type, node_id="node-2")
    CollectInstanceOrganization.objects.create(collect_instance=bound, organization=1)
    CollectInstanceOrganization.objects.create(collect_instance=unbound, organization=1)
    CollectInstanceOrganization.objects.create(collect_instance=foreign, organization=2)
    LogExtractor.objects.create(
        name="copy-bound",
        collect_instance=bound,
        extractor_type=LogExtractor.ExtractorType.COPY,
        sort_order=1,
        config={},
    )
    policy = Policy.objects.create(
        name="p-org",
        collect_type=collect_type,
        alert_type="keyword",
        alert_name="a",
        alert_level="warning",
    )
    PolicyOrganization.objects.create(policy=policy, organization=1)
    other_policy = Policy.objects.create(
        name="p-other",
        collect_type=collect_type,
        alert_type="keyword",
        alert_name="b",
        alert_level="warning",
    )
    PolicyOrganization.objects.create(policy=other_policy, organization=2)

    result = log_nats.get_log_usage_statistics(user_info=_user_info())

    assert result["result"] is True
    assert result["data"]["collect_instance_count"] == 2
    assert result["data"]["bound_instance_count"] == 1
    assert result["data"]["bound_instance_rate"] == 50.0
    assert result["data"]["extractor_count"] == 1
    assert result["data"]["policy_count"] == 1


def test_log_usage_statistics_forged_org_outside_group_tree_is_zero(mocker):
    _grant(mocker, team=2)
    collect_type = CollectType.objects.create(name="file-forged", collector="Vector", icon="")
    foreign = CollectInstance.objects.create(id="log-forged", name="forged", collect_type=collect_type, node_id="node-x")
    CollectInstanceOrganization.objects.create(collect_instance=foreign, organization=2)
    policy = Policy.objects.create(
        name="p-forged",
        collect_type=collect_type,
        alert_type="keyword",
        alert_name="a",
        alert_level="warning",
    )
    PolicyOrganization.objects.create(policy=policy, organization=2)

    result = log_nats.get_log_usage_statistics(
        user_info={
            **_user_info(team=2),
            "group_tree": [{"id": 1, "subGroups": []}],
        }
    )

    assert result["result"] is True
    assert result["data"] == {
        "collect_instance_count": 0,
        "extractor_count": 0,
        "policy_count": 0,
        "bound_instance_count": 0,
        "bound_instance_rate": 0,
    }


def test_log_usage_statistics_include_children_queries_permission_with_selected_team(mocker):
    grant = mocker.patch("apps.log.nats.log.get_permission_rules", return_value={"team": [1, 9]})
    mocker.patch(
        "apps.system_mgmt.utils.group_utils.GroupUtils.get_group_with_descendants",
        return_value=[9, 1],
    )

    log_nats.get_log_usage_statistics(user_info={**_user_info(team=1), "include_children": True})

    assert grant.call_count == 2
    assert [call.args[1] for call in grant.call_args_list] == [1, 1]


def test_log_policy_alert_top_uses_time_window_and_org(mocker):
    _grant(mocker)
    collect_type = CollectType.objects.create(name="file2", collector="Vector", icon="")
    policy = Policy.objects.create(
        name="hot-policy",
        collect_type=collect_type,
        alert_type="keyword",
        alert_name="a",
        alert_level="warning",
    )
    PolicyOrganization.objects.create(policy=policy, organization=1)
    other = Policy.objects.create(
        name="other-policy",
        collect_type=collect_type,
        alert_type="keyword",
        alert_name="b",
        alert_level="warning",
    )
    PolicyOrganization.objects.create(policy=other, organization=2)
    start = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    end = start + timedelta(days=1)
    for index in range(2):
        alert = Alert.objects.create(
            id=f"log-alert-{index}",
            policy=policy,
            source_id="src",
            collect_type=collect_type,
        )
        Alert.objects.filter(pk=alert.pk).update(created_at=start + timedelta(hours=1))
    foreign = Alert.objects.create(id="log-alert-foreign", policy=other, source_id="src", collect_type=collect_type)
    Alert.objects.filter(pk=foreign.pk).update(created_at=start + timedelta(hours=1))

    result = log_nats.get_log_policy_alert_top(
        user_info=_user_info(),
        limit=10,
        time=[start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")],
    )

    assert result["result"] is True
    assert result["data"] == [{"policy_id": policy.id, "policy_name": "hot-policy", "count": 2}]


def test_log_policy_alert_top_clamps_limit_to_100(mocker):
    _grant(mocker)
    collect_type = CollectType.objects.create(name="file-cap", collector="Vector", icon="")
    start = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    end = start + timedelta(days=1)
    policies = Policy.objects.bulk_create(
        [
            Policy(
                name=f"cap-policy-{index}",
                collect_type=collect_type,
                alert_type="keyword",
                alert_name="a",
                alert_level="warning",
            )
            for index in range(101)
        ]
    )
    if any(policy.pk is None for policy in policies):
        policies = list(Policy.objects.filter(name__startswith="cap-policy-").order_by("id"))
    PolicyOrganization.objects.bulk_create([PolicyOrganization(policy=policy, organization=1) for policy in policies])
    Alert.objects.bulk_create([Alert(id=f"log-cap-{policy.id}", policy=policy, source_id="src", collect_type=collect_type) for policy in policies])
    Alert.objects.filter(id__startswith="log-cap-").update(created_at=start + timedelta(hours=1))

    result = log_nats.get_log_policy_alert_top(
        user_info=_user_info(),
        limit=10**9,
        time=[start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")],
    )

    assert result["result"] is True
    assert len(result["data"]) == 100
