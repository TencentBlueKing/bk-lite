"""Issue 5852：组织策略覆盖查询不得随策略条数线性增长。"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

import apps.node_mgmt  # noqa: F401 - monitor.nats.monitor 启动依赖
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.nats.monitor import _policy_covered_instance_ids

pytestmark = pytest.mark.django_db


def _org_membership_selects(captured_queries):
    table = MonitorInstanceOrganization._meta.db_table.lower()
    selects = []
    for query in captured_queries:
        sql = query["sql"].lstrip()
        if table in sql.lower() and sql.lower().startswith("select"):
            selects.append(sql)
    return selects


def _make_policy(monitor_object, name, source, enable=True):
    return MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name=name,
        algorithm="max",
        query_condition={},
        source=source,
        group_by=[],
        enable=enable,
        threshold=[{"method": ">", "value": 1, "level": "warning"}],
    )


def _legacy_covered_instance_ids(policy_qs, instance_qs):
    instance_ids = set(instance_qs.values_list("id", flat=True))
    covered = set()
    for policy in policy_qs.filter(enable=True).only("id", "monitor_object_id", "source"):
        source = policy.source if isinstance(policy.source, dict) else {}
        source_type = source.get("type")
        source_values = source.get("values") or []
        if source_type == "instance":
            covered.update(value for value in source_values if value in instance_ids)
            continue
        if source_type == "organization":
            covered.update(
                MonitorInstanceOrganization.objects.filter(
                    monitor_instance__monitor_object_id=policy.monitor_object_id,
                    monitor_instance_id__in=instance_ids,
                    organization__in=source_values,
                ).values_list("monitor_instance_id", flat=True)
            )
            continue
        covered.update(instance_qs.filter(monitor_object_id=policy.monitor_object_id).values_list("id", flat=True))
    return covered


def test_organization_policy_coverage_batches_membership_queries():
    obj_a = MonitorObject.objects.create(name="issue-5852-obj-a", level="base")
    obj_b = MonitorObject.objects.create(name="issue-5852-obj-b", level="base")

    covered_org1 = MonitorInstance.objects.create(id="issue-5852-org1", name="org1", monitor_object=obj_a)
    covered_org2 = MonitorInstance.objects.create(id="issue-5852-org2", name="org2", monitor_object=obj_a)
    uncovered = MonitorInstance.objects.create(id="issue-5852-bare", name="bare", monitor_object=obj_a)
    other_object = MonitorInstance.objects.create(id="issue-5852-objb", name="objb", monitor_object=obj_b)
    instance_typed = MonitorInstance.objects.create(id="issue-5852-inst", name="inst", monitor_object=obj_a)
    other_type_inst = MonitorInstance.objects.create(id="issue-5852-all", name="all", monitor_object=obj_b)

    MonitorInstanceOrganization.objects.create(monitor_instance=covered_org1, organization=1)
    MonitorInstanceOrganization.objects.create(monitor_instance=covered_org2, organization=2)
    MonitorInstanceOrganization.objects.create(monitor_instance=uncovered, organization=3)
    MonitorInstanceOrganization.objects.create(monitor_instance=other_object, organization=1)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance_typed, organization=3)
    MonitorInstanceOrganization.objects.create(monitor_instance=other_type_inst, organization=9)

    instance_qs = MonitorInstance.objects.filter(
        id__in=[
            covered_org1.id,
            covered_org2.id,
            uncovered.id,
            other_object.id,
            instance_typed.id,
            other_type_inst.id,
        ]
    )

    org_p1 = _make_policy(obj_a, "issue-5852-org-1", {"type": "organization", "values": [1]})
    org_p2 = _make_policy(obj_a, "issue-5852-org-2", {"type": "organization", "values": [2]})
    instance_policy = _make_policy(obj_a, "issue-5852-inst-src", {"type": "instance", "values": [instance_typed.id]})
    other_type_policy = _make_policy(obj_b, "issue-5852-no-type", {})
    disabled_policy = _make_policy(obj_a, "issue-5852-disabled-org", {"type": "organization", "values": [3]}, enable=False)

    two_policy_ids = [org_p1.id, org_p2.id, instance_policy.id, other_type_policy.id, disabled_policy.id]
    two_qs = MonitorPolicy.objects.filter(id__in=two_policy_ids)
    expected = _legacy_covered_instance_ids(two_qs, instance_qs)

    with CaptureQueriesContext(connection) as two_ctx:
        covered_two = _policy_covered_instance_ids(two_qs, instance_qs)
    two_org_queries = _org_membership_selects(two_ctx.captured_queries)

    org_p3 = _make_policy(obj_a, "issue-5852-org-1b", {"type": "organization", "values": [1]})
    org_p4 = _make_policy(obj_a, "issue-5852-org-2b", {"type": "organization", "values": [2]})
    four_qs = MonitorPolicy.objects.filter(id__in=[*two_policy_ids, org_p3.id, org_p4.id])
    expected_four = _legacy_covered_instance_ids(four_qs, instance_qs)

    with CaptureQueriesContext(connection) as four_ctx:
        covered_four = _policy_covered_instance_ids(four_qs, instance_qs)
    four_org_queries = _org_membership_selects(four_ctx.captured_queries)

    assert covered_org1.id in covered_two
    assert covered_org2.id in covered_two
    assert instance_typed.id in covered_two
    assert other_object.id in covered_two
    assert other_type_inst.id in covered_two
    assert uncovered.id not in covered_two
    assert covered_two == expected
    assert covered_four == expected_four
    assert covered_four == expected
    assert len(two_org_queries) == len(four_org_queries)
    assert len(four_org_queries) <= 2
