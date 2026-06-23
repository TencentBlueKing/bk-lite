"""CollectTypeService 服务层真实行为测试。

只 mock RPC 边界（Controller / NodeMgmt），DB 走真实。
覆盖 batch_create_collect_configs / set_instances_organizations /
update_instance_config / _extract_update_payload / get_collect_type。
"""
import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.models import (
    CollectConfig,
    CollectInstance,
    CollectInstanceOrganization,
    CollectType,
)
from apps.log.services.collect_type import CollectTypeService


# --------------------------- 纯函数 ---------------------------


def test_get_collect_type_lowercases():
    assert CollectTypeService.get_collect_type("File") == "file"


def test_get_collect_type_none_returns_unknown():
    assert CollectTypeService.get_collect_type("") == "unknown"
    assert CollectTypeService.get_collect_type(None) == "unknown"


def test_extract_update_payload_returns_content():
    assert CollectTypeService._extract_update_payload({"content": "abc"}, "base") == "abc"


def test_extract_update_payload_missing_content_raises():
    with pytest.raises(BaseAppException) as exc:
        CollectTypeService._extract_update_payload({}, "base")
    assert "content is required" in str(exc.value)


# --------------------------- batch_create_collect_configs ---------------------------


@pytest.fixture
def collect_type(db):
    return CollectType.objects.create(name="file", collector="Vector", icon="file")


@pytest.mark.django_db
def test_batch_create_rejects_instance_without_single_node(collect_type):
    data = {
        "collect_type_id": collect_type.id,
        "collector": "Vector",
        "instances": [
            {"instance_id": "i-1", "instance_name": "实例1", "node_ids": [], "group_ids": [1]},
        ],
    }
    with pytest.raises(BaseAppException) as exc:
        CollectTypeService.batch_create_collect_configs(data)
    assert "必须关联且仅关联一个节点" in str(exc.value)
    assert not CollectInstance.objects.filter(id="i-1").exists()


@pytest.mark.django_db
def test_batch_create_rejects_existing_instance(collect_type):
    CollectInstance.objects.create(id="i-exist", name="已存在", collect_type=collect_type)
    data = {
        "collect_type_id": collect_type.id,
        "collector": "Vector",
        "instances": [
            {"instance_id": "i-exist", "instance_name": "已存在", "node_ids": ["n-1"], "group_ids": [1]},
        ],
    }
    with pytest.raises(BaseAppException) as exc:
        CollectTypeService.batch_create_collect_configs(data)
    assert "以下实例已存在" in str(exc.value)


@pytest.mark.django_db
def test_batch_create_no_new_instances_returns_early(collect_type, mocker):
    """所有实例都已存在会先被上面的分支拦截；此处验证空 instances 列表不会创建。"""
    controller = mocker.patch("apps.log.services.collect_type.Controller")
    data = {"collect_type_id": collect_type.id, "collector": "Vector", "instances": []}
    result = CollectTypeService.batch_create_collect_configs(data)
    assert result is None
    controller.assert_not_called()


@pytest.mark.django_db
def test_batch_create_success_creates_instances_orgs_and_calls_controller(collect_type, mocker):
    controller_cls = mocker.patch("apps.log.services.collect_type.Controller")
    data = {
        "collect_type_id": collect_type.id,
        "collector": "Vector",
        "configs": [],
        "instances": [
            {"instance_id": "new-1", "instance_name": "新实例", "node_ids": ["node-a"], "group_ids": [1, 2]},
        ],
    }

    CollectTypeService.batch_create_collect_configs(data)

    instance = CollectInstance.objects.get(id="new-1")
    assert instance.name == "新实例"
    assert instance.node_id == "node-a"
    assert instance.collect_type_id == collect_type.id
    orgs = set(
        CollectInstanceOrganization.objects.filter(collect_instance_id="new-1").values_list("organization", flat=True)
    )
    assert orgs == {1, 2}
    # Controller 被调用且收到 new_instances
    controller_cls.assert_called_once()
    controller_cls.return_value.controller.assert_called_once()


@pytest.mark.django_db
def test_batch_create_rolls_back_when_controller_fails(collect_type, mocker):
    """Controller 抛业务异常时外层事务回滚，实例不应残留。"""
    controller_cls = mocker.patch("apps.log.services.collect_type.Controller")
    controller_cls.return_value.controller.side_effect = BaseAppException("RPC 失败")
    data = {
        "collect_type_id": collect_type.id,
        "collector": "Vector",
        "configs": [],
        "instances": [
            {"instance_id": "rb-1", "instance_name": "回滚实例", "node_ids": ["node-a"], "group_ids": [1]},
        ],
    }

    with pytest.raises(BaseAppException):
        CollectTypeService.batch_create_collect_configs(data)

    assert not CollectInstance.objects.filter(id="rb-1").exists()
    assert not CollectInstanceOrganization.objects.filter(collect_instance_id="rb-1").exists()


@pytest.mark.django_db
def test_batch_create_wraps_unexpected_exception(collect_type, mocker):
    controller_cls = mocker.patch("apps.log.services.collect_type.Controller")
    controller_cls.return_value.controller.side_effect = RuntimeError("boom")
    data = {
        "collect_type_id": collect_type.id,
        "collector": "Vector",
        "configs": [],
        "instances": [
            {"instance_id": "wrap-1", "instance_name": "包装实例", "node_ids": ["node-a"], "group_ids": [1]},
        ],
    }

    with pytest.raises(BaseAppException) as exc:
        CollectTypeService.batch_create_collect_configs(data)
    assert "创建采集配置失败" in str(exc.value)
    assert not CollectInstance.objects.filter(id="wrap-1").exists()


# --------------------------- set_instances_organizations ---------------------------


@pytest.mark.django_db
def test_set_instances_organizations_noop_on_empty(collect_type):
    CollectInstance.objects.create(id="so-1", name="x", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance_id="so-1", organization=9)
    # 空 organizations -> 直接返回，不删除现有关联
    CollectTypeService.set_instances_organizations(["so-1"], [])
    assert CollectInstanceOrganization.objects.filter(collect_instance_id="so-1", organization=9).exists()


@pytest.mark.django_db
def test_set_instances_organizations_replaces_existing(collect_type):
    CollectInstance.objects.create(id="so-2", name="x", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance_id="so-2", organization=1)

    CollectTypeService.set_instances_organizations(["so-2"], [5, 6])

    orgs = set(
        CollectInstanceOrganization.objects.filter(collect_instance_id="so-2").values_list("organization", flat=True)
    )
    assert orgs == {5, 6}


# --------------------------- update_instance_config ---------------------------


@pytest.mark.django_db
def test_update_instance_config_updates_base_and_child(collect_type, mocker):
    inst = CollectInstance.objects.create(id="ci-1", name="ci1", collect_type=collect_type)
    base = CollectConfig.objects.create(id="cfg-base", collect_instance=inst, file_type="yaml", is_child=False)
    child = CollectConfig.objects.create(id="cfg-child", collect_instance=inst, file_type="toml", is_child=True)
    node_mgmt = mocker.patch("apps.log.services.collect_type.NodeMgmt").return_value

    CollectTypeService.update_instance_config(
        child_info={"id": child.id, "content": {"a": 1}},
        base_info={"id": base.id, "content": {"b": 2}, "env_config": {"K": "V"}},
    )

    node_mgmt.update_config_content.assert_called_once()
    base_call = node_mgmt.update_config_content.call_args.args
    assert base_call[0] == base.id
    assert node_mgmt.update_child_config_content.call_count == 1
    child_call = node_mgmt.update_child_config_content.call_args.args
    assert child_call[0] == child.id


@pytest.mark.django_db
def test_update_instance_config_skips_missing_child_config(collect_type, mocker):
    inst = CollectInstance.objects.create(id="ci-2", name="ci2", collect_type=collect_type)
    base = CollectConfig.objects.create(id="cfg-b2", collect_instance=inst, file_type="yaml", is_child=False)
    node_mgmt = mocker.patch("apps.log.services.collect_type.NodeMgmt").return_value

    # child_info 指向不存在的配置，child 分支应提前 return（不调用 child RPC）
    CollectTypeService.update_instance_config(
        child_info={"id": "missing-child", "content": {"a": 1}},
        base_info={"id": base.id, "content": {"b": 2}},
    )

    node_mgmt.update_config_content.assert_called_once()
    node_mgmt.update_child_config_content.assert_not_called()
