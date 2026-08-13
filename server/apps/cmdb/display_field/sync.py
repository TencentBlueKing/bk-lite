# -- coding: utf-8 --
"""
显示字段同步工具

职责：
当用户或组织的展示数据发生变化时，同步更新所有实例的 _display 字段值

使用场景：
1. 组织名称变更：更新所有包含该组织的实例的 organization_display 字段
2. 用户显示名变更：更新所有包含该用户的实例的相关 _display 字段

数据格式示例：
{
    "organizations": [{"id": 1, "name": "Default1"}],
    "users": [{"id": 1, "username": "admin", "display_name": "超级管理员111"}]
}

字段映射关系：
- 组织: 原始字段存储 id, display字段存储 name
- 用户: 原始字段存储 id, display字段存储 display_name(username)
"""

import os
from collections import defaultdict
from typing import Any, Dict, List

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.display_field.constants import DISPLAY_SUFFIX, DISPLAY_VALUES_SEPARATOR, USER_DISPLAY_FORMAT
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.graph.validators import MAX_BATCH_UPDATE_PROPERTY_VALUES
from apps.core.logger import cmdb_logger as logger
from apps.system_mgmt.models import Group, User

DEFAULT_SYNC_BATCH_SIZE = 500


def _get_sync_batch_size() -> int:
    raw_value = os.getenv("CMDB_DISPLAY_SYNC_BATCH_SIZE", str(DEFAULT_SYNC_BATCH_SIZE))
    try:
        batch_size = max(1, int(raw_value))
    except (TypeError, ValueError):
        logger.warning(
            "[DisplayFieldSynchronizer] CMDB_DISPLAY_SYNC_BATCH_SIZE=%r 非法，使用默认值 %s",
            raw_value,
            DEFAULT_SYNC_BATCH_SIZE,
        )
        return DEFAULT_SYNC_BATCH_SIZE
    if batch_size > MAX_BATCH_UPDATE_PROPERTY_VALUES:
        logger.warning(
            "[DisplayFieldSynchronizer] CMDB_DISPLAY_SYNC_BATCH_SIZE=%s 超过图写上限，限制为 %s",
            batch_size,
            MAX_BATCH_UPDATE_PROPERTY_VALUES,
        )
        return MAX_BATCH_UPDATE_PROPERTY_VALUES
    return batch_size


def _format_user_display(user: Dict[str, Any]) -> str:
    username = user.get("username", "")
    display_name = user.get("display_name", "")
    if display_name and display_name.strip():
        return USER_DISPLAY_FORMAT.format(display_name=display_name, username=username)
    return username


def _match_organization_fields(instance, field_ids, org_ids, org_map):
    matched_fields = []
    missing_ids = set()
    for field_id in field_ids:
        field_value = instance.get(field_id)
        if not field_value:
            continue
        field_values = field_value if isinstance(field_value, list) else [field_value]
        if not set(field_values) & org_ids:
            continue
        matched_fields.append((field_id, field_values))
        missing_ids.update(value for value in field_values if value not in org_map)
    return matched_fields, missing_ids


def _match_user_fields(instance, field_ids, user_ids, user_map):
    matched_fields = []
    missing_ids = set()
    for field_id in field_ids:
        field_value = instance.get(field_id)
        if not field_value:
            continue
        if isinstance(field_value, (int, str)):
            field_values = [int(field_value)]
        else:
            field_values = [int(value) for value in field_value]
        if not set(field_values) & user_ids:
            continue
        matched_fields.append((field_id, field_values))
        missing_ids.update(value for value in field_values if value not in user_map)
    return matched_fields, missing_ids


def _collect_pending_updates(instances, model_fields_mapping, org_map, user_map):
    pending_updates = []
    missing_org_ids = set()
    missing_user_ids = set()
    org_ids = set(org_map)
    user_ids = set(user_map)

    for instance in instances:
        model_mapping = model_fields_mapping.get(instance.get("model_id"), {})
        matched_org_fields, instance_missing_org_ids = _match_organization_fields(
            instance, model_mapping.get("organization", []) if org_map else [], org_ids, org_map
        )
        matched_user_fields, instance_missing_user_ids = _match_user_fields(
            instance, model_mapping.get("user", []) if user_map else [], user_ids, user_map
        )
        missing_org_ids.update(instance_missing_org_ids)
        missing_user_ids.update(instance_missing_user_ids)
        if matched_org_fields or matched_user_fields:
            pending_updates.append((instance["_id"], matched_org_fields, matched_user_fields))

    return pending_updates, missing_org_ids, missing_user_ids


def _load_missing_references(missing_org_ids, missing_user_ids):
    group_map = {}
    if missing_org_ids:
        group_map = dict(Group.objects.filter(id__in=sorted(missing_org_ids)).values_list("id", "name"))

    missing_user_map = {}
    if missing_user_ids:
        missing_user_map = {
            user["id"]: user for user in User.objects.filter(id__in=sorted(missing_user_ids)).values("id", "username", "display_name")
        }
    return group_map, missing_user_map


def _append_organization_updates(field_updates, node_id, matched_fields, org_map, group_map):
    for field_id, field_values in matched_fields:
        display_names = [org_map[value] for value in field_values if value in org_map]
        display_names.extend(group_map[value] for value in field_values if value not in org_map and value in group_map)
        field_updates[f"{field_id}{DISPLAY_SUFFIX}"].append({"id": node_id, "value": DISPLAY_VALUES_SEPARATOR.join(display_names)})


def _append_user_updates(field_updates, node_id, matched_fields, user_map, missing_user_map):
    for field_id, field_values in matched_fields:
        display_names = [_format_user_display(user_map[value]) for value in field_values if value in user_map]
        display_names.extend(
            _format_user_display(missing_user_map[value]) for value in field_values if value not in user_map and value in missing_user_map
        )
        field_updates[f"{field_id}{DISPLAY_SUFFIX}"].append({"id": node_id, "value": DISPLAY_VALUES_SEPARATOR.join(display_names)})


def _update_instance_page(ag, instances, model_fields_mapping, org_map, user_map):
    pending_updates, missing_org_ids, missing_user_ids = _collect_pending_updates(instances, model_fields_mapping, org_map, user_map)
    group_map, missing_user_map = _load_missing_references(missing_org_ids, missing_user_ids)

    field_updates = defaultdict(list)
    org_updated_count = 0
    user_updated_count = 0
    for node_id, matched_org_fields, matched_user_fields in pending_updates:
        org_updated_count += bool(matched_org_fields)
        user_updated_count += bool(matched_user_fields)
        _append_organization_updates(field_updates, node_id, matched_org_fields, org_map, group_map)
        _append_user_updates(field_updates, node_id, matched_user_fields, user_map, missing_user_map)

    # 每个展示字段在本批只发起一次图写，同一批中不同实例可携带不同值。
    for field_id, property_values in field_updates.items():
        ag.batch_update_node_property_values(INSTANCE, field_id, property_values)
    return org_updated_count, user_updated_count


class DisplayFieldSynchronizer:
    """
    显示字段同步器

    当组织/用户的展示信息变更时，同步更新所有实例的 _display 冗余字段
    传入的数据已包含最新的原始值和展示值，无需再次查询数据库
    """

    @staticmethod
    def sync_all(data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
        """
        同步所有类型的展示字段变更（统一循环处理组织和用户）

        Args:
            data: 变更数据字典
                格式: {
                    "organizations": [{"id": 1, "name": "Default1"}],
                    "users": [{"id": 1, "username": "admin", "display_name": "超级管理员111"}]
                }

        Returns:
            Dict[str, int]: 各类型更新的实例数量
                格式: {"organizations": 10, "users": 5}
        """
        organizations = data.get("organizations", [])
        users = data.get("users", [])

        # 如果两者都为空，直接返回
        if not organizations and not users:
            logger.warning("[DisplayFieldSynchronizer] 组织和用户数据均为空，跳过同步")
            return {"organizations": 0, "users": 0}

        # 构建映射表
        org_map = {org["id"]: org["name"] for org in organizations} if organizations else {}
        # 用户映射存储完整信息：{'username': 'admin', 'display_name': '管理员'}
        user_map = (
            {user["id"]: {"username": user.get("username", ""), "display_name": user.get("display_name", "")} for user in users} if users else {}
        )
        org_updated_count = 0
        user_updated_count = 0

        try:
            # 从缓存获取模型字段映射
            from apps.cmdb.display_field.cache import ExcludeFieldsCache

            model_fields_mapping = ExcludeFieldsCache.get_model_fields_mapping()

            candidate_model_ids = sorted(
                model_id
                for model_id, mapping in model_fields_mapping.items()
                if (org_map and mapping.get("organization")) or (user_map and mapping.get("user"))
            )
            if not candidate_model_ids:
                return {"organizations": 0, "users": 0}

            batch_size = _get_sync_batch_size()
            with GraphClient() as ag:
                cursor = None
                while True:
                    query_params = [{"field": "model_id", "type": "str[]", "value": candidate_model_ids}]
                    if cursor is not None:
                        query_params.append({"field": "id", "type": "id>", "value": cursor})

                    instances, _ = ag.query_entity(
                        INSTANCE,
                        query_params,
                        page={"skip": 0, "limit": batch_size},
                        include_count=False,
                    )
                    if not instances:
                        break

                    page_org_count, page_user_count = _update_instance_page(ag, instances, model_fields_mapping, org_map, user_map)
                    org_updated_count += page_org_count
                    user_updated_count += page_user_count

                    cursor = instances[-1]["_id"]
                    if len(instances) < batch_size:
                        break

                result = {"organizations": org_updated_count, "users": user_updated_count}

                if org_updated_count > 0 or user_updated_count > 0:
                    logger.info(f"[DisplayFieldSynchronizer] 同步完成, " f"组织更新实例数: {org_updated_count}, " f"用户更新实例数: {user_updated_count}")

                return result

        except Exception as e:
            logger.error(f"[DisplayFieldSynchronizer] 同步 _display 字段失败: {e}", exc_info=True)
            raise

    @staticmethod
    def sync_organization_display(organizations: List[Dict[str, Any]]) -> int:
        """
        同步组织名称变更到所有实例的 organization_display 字段

        注意：推荐使用 sync_all() 方法，性能更优

        Args:
            organizations: 组织变更数据列表，包含最新的 id 和 name
                格式: [{"id": 1, "name": "新组织名"}]

        Returns:
            int: 更新的实例数量
        """
        result = DisplayFieldSynchronizer.sync_all({"organizations": organizations})
        return result.get("organizations", 0)

    @staticmethod
    def sync_user_display(users: List[Dict[str, str]]) -> int:
        """
        同步用户显示名变更到所有实例的用户类型 _display 字段

        注意：推荐使用 sync_all() 方法，性能更优

        Args:
            users: 用户变更数据列表，包含最新的 id、username 和 display_name
                格式: [{"id": 1, "username": "admin", "display_name": "超级管理员111"}]

        Returns:
            int: 更新的实例数量
        """
        result = DisplayFieldSynchronizer.sync_all({"users": users})
        return result.get("users", 0)


# ========== 系统管理调用入口 ==========


def sync_display_fields_for_system_mgmt(organizations: List[Dict[str, Any]] = None, users: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    系统管理调用入口：同步组织/用户的 _display 字段

    当系统管理模块修改组织或用户信息时，调用此函数同步更新 CMDB 实例的 _display 字段
    该函数会触发 Celery 异步任务处理，避免阻塞主流程

    Args:
        organizations: 组织变更数据列表
            格式: [{"id": 1, "name": "新组织名"}]
        users: 用户变更数据列表
            格式: [{"id": 1, "username": "admin", "display_name": "新显示名"}]

    Returns:
        Dict[str, Any]: 任务提交结果
            格式: {"task_id": "uuid", "status": "submitted"}

    Usage:
        # 在系统管理的组织/用户更新接口中调用
        from apps.cmdb.display_field import sync_display_fields_for_system_mgmt

        # 组织名称变更
        sync_display_fields_for_system_mgmt(
            organizations=[{"id": 1, "name": "新组织名"}]
        )

        # 用户显示名变更
        sync_display_fields_for_system_mgmt(
            users=[{"id": 1, "username": "admin", "display_name": "新显示名"}]
        )

        # 同时更新组织和用户
        sync_display_fields_for_system_mgmt(
            organizations=[{"id": 1, "name": "新组织名"}],
            users=[{"id": 1, "username": "admin", "display_name": "新显示名"}]
        )
    """
    data = {}
    if organizations:
        data["organizations"] = organizations
    if users:
        data["users"] = users

    if not data:
        logger.warning("[DisplayFieldSync] 组织和用户数据均为空，跳过同步")
        return {"task_id": None, "status": "skipped"}

    # 触发异步任务处理
    from apps.cmdb.tasks.celery_tasks import sync_cmdb_display_fields_task

    task = sync_cmdb_display_fields_task.delay(data)

    logger.info(
        f"[DisplayFieldSync] 已提交异步任务, task_id: {task.id}, "
        f"组织数: {len(organizations) if organizations else 0}, "
        f"用户数: {len(users) if users else 0}"
    )

    return {"task_id": str(task.id), "status": "submitted"}
