"""apps/log/nats/permission.py 测试：get_log_module_data / get_log_module_list。

真实 DB，覆盖三种 module 分支、分页、非法 module、模块列表结构。
"""
import pytest

from apps.log.models import CollectInstance, CollectType, LogGroup
from apps.log.models.instance import CollectInstanceOrganization
from apps.log.models.log_group import LogGroupOrganization
from apps.log.models.policy import Policy, PolicyOrganization
from apps.log.nats.permission import get_log_module_data, get_log_module_list

pytestmark = pytest.mark.django_db


@pytest.fixture
def collect_type():
    return CollectType.objects.create(name="nginx", collector="Filebeat")


class TestGetLogModuleData:
    def test_log_group_module(self):
        group = LogGroup.objects.create(id="lg-1", name="g1", rule={})
        LogGroupOrganization.objects.create(log_group=group, organization=1)
        result = get_log_module_data("log_group", None, 1, 10, 1)
        assert result["count"] == 1
        assert result["items"][0]["name"] == "g1"

    def test_policy_module(self, collect_type):
        policy = Policy.objects.create(
            name="p1",
            collect_type=collect_type,
            alert_type="keyword",
            alert_name="a",
            alert_level="warning",
        )
        PolicyOrganization.objects.create(policy=policy, organization=2)
        result = get_log_module_data("policy", collect_type.id, 1, 10, 2)
        assert result["count"] == 1
        assert result["items"][0]["id"] == policy.id

    def test_instance_module(self, collect_type):
        instance = CollectInstance.objects.create(id="i1", name="inst1", collect_type=collect_type)
        CollectInstanceOrganization.objects.create(collect_instance=instance, organization=3)
        result = get_log_module_data("instance", collect_type.id, 1, 10, 3)
        assert result["count"] == 1
        assert result["items"][0]["name"] == "inst1"

    def test_pagination(self):
        for i in range(5):
            g = LogGroup.objects.create(id=f"lg-page-{i}", name=f"g{i}", rule={})
            LogGroupOrganization.objects.create(log_group=g, organization=9)
        page1 = get_log_module_data("log_group", None, 1, 2, 9)
        page2 = get_log_module_data("log_group", None, 2, 2, 9)
        assert page1["count"] == 5
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        # 不同页数据不重叠
        ids1 = {x["id"] for x in page1["items"]}
        ids2 = {x["id"] for x in page2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_invalid_module_raises(self):
        with pytest.raises(ValueError, match="Invalid module type"):
            get_log_module_data("unknown", None, 1, 10, 1)


class TestGetLogModuleList:
    def test_structure_includes_collect_types_as_children(self, collect_type):
        result = get_log_module_list()
        names = [item["name"] for item in result]
        assert names == ["log_group", "policy", "instance"]
        # policy / instance 的 children 含采集类型
        policy_node = next(item for item in result if item["name"] == "policy")
        child_ids = [c["name"] for c in policy_node["children"]]
        assert collect_type.id in child_ids

    def test_log_group_has_no_children(self):
        result = get_log_module_list()
        lg = next(item for item in result if item["name"] == "log_group")
        assert lg["children"] == []
