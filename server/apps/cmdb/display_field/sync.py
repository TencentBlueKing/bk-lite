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

from typing import List, Dict, Any

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.display_field.constants import (
    DISPLAY_SUFFIX,
    DISPLAY_VALUES_SEPARATOR,
    USER_DISPLAY_FORMAT,
)
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.core.logger import cmdb_logger as logger
from apps.system_mgmt.models import User, Group


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
        user_map = {
            user["id"]: {
                'username': user.get('username', ''),
                'display_name': user.get('display_name', '')
            }
            for user in users
        } if users else {}
        org_ids = set(org_map.keys())
        user_ids = set(user_map.keys())
        
        org_updated_count = 0
        user_updated_count = 0
        
        try:
            # 从缓存获取模型字段映射
            from apps.cmdb.display_field.cache import ExcludeFieldsCache
            model_fields_mapping = ExcludeFieldsCache.get_model_fields_mapping()
            
            with GraphClient() as ag:
                # 查询所有实例
                all_instances, _ = ag.query_entity(INSTANCE, [])
                
                # 统一循环处理所有实例
                for instance in all_instances:
                    model_id = instance.get("model_id")
                    if not model_id:
                        continue
                    
                    # 从缓存获取该模型的字段映射
                    model_mapping = model_fields_mapping.get(model_id, {})
                    org_fields = model_mapping.get('organization', [])
                    user_fields = model_mapping.get('user', [])
                    
                    # 如果该模型既没有组织字段也没有用户字段，跳过
                    if not org_fields and not user_fields:
                        continue
                    
                    update_data = {}
                    has_org_update = False
                    has_user_update = False
                    
                    # 处理组织字段
                    if org_fields and org_map:
                        for org_field in org_fields:
                            instance_org_ids = instance.get(org_field)
                            if not instance_org_ids:
                                continue
                            
                            # 确保是列表格式
                            if not isinstance(instance_org_ids, list):
                                instance_org_ids = [instance_org_ids]
                            
                            # 检查实例的组织ID是否与变更的组织ID有交集
                            if not set(instance_org_ids) & org_ids:
                                continue
                            
                            # 重新构建 _display 字段
                            display_names = []
                            missing_ids = []
                            
                            for org_id in instance_org_ids:
                                if org_id in org_map:
                                    display_names.append(org_map[org_id])
                                else:
                                    missing_ids.append(org_id)
                            
                            # 查询映射表中不存在的组织名称
                            if missing_ids:
                                missing_groups = Group.objects.filter(id__in=missing_ids).values_list('name', flat=True)
                                display_names.extend(missing_groups)
                            
                            display_field = f"{org_field}{DISPLAY_SUFFIX}"
                            new_display_value = DISPLAY_VALUES_SEPARATOR.join(display_names)
                            update_data[display_field] = new_display_value
                            has_org_update = True
                    
                    # 处理用户字段
                    if user_fields and user_map:
                        for field_id in user_fields:
                            field_value = instance.get(field_id)
                            if not field_value:
                                continue
                            
                            # user 字段可能是单个用户ID或用户ID列表
                            if isinstance(field_value, (int, str)):
                                field_value_list = [int(field_value)]
                            else:
                                field_value_list = [int(v) for v in field_value]
                            
                            # 检查是否包含变更的用户
                            if not set(field_value_list) & user_ids:
                                continue
                            
                            # 重新构建 _display 值（格式：display_name(username)）
                            display_names = []
                            missing_ids = []
                            
                            for user_id in field_value_list:
                                if user_id in user_map:
                                    user_info = user_map[user_id]
                                    username = user_info.get('username', '')
                                    display_name = user_info.get('display_name', '')
                                    
                                    # 格式化为 USER_DISPLAY_FORMAT 格式
                                    if display_name and display_name.strip():
                                        display_names.append(USER_DISPLAY_FORMAT.format(
                                            display_name=display_name,
                                            username=username
                                        ))
                                    else:
                                        display_names.append(username)
                                else:
                                    missing_ids.append(user_id)
                            
                            # 查询映射表中不存在的用户信息
                            if missing_ids:
                                missing_users = User.objects.filter(id__in=missing_ids).values("username", "display_name")
                                for user in missing_users:
                                    username = user.get('username', '')
                                    display_name = user.get('display_name', '')
                                    
                                    if display_name and display_name.strip():
                                        display_names.append(USER_DISPLAY_FORMAT.format(
                                            display_name=display_name,
                                            username=username
                                        ))
                                    else:
                                        display_names.append(username)
                            
                            display_field_id = f"{field_id}{DISPLAY_SUFFIX}"
                            new_display_value = DISPLAY_VALUES_SEPARATOR.join(display_names)
                            update_data[display_field_id] = new_display_value
                            has_user_update = True
                    
                    # 如果有需要更新的字段，批量更新
                    if update_data:
                        ag.batch_update_node_properties(
                            INSTANCE,
                            [instance["_id"]],
                            update_data
                        )
                        if has_org_update:
                            org_updated_count += 1
                        if has_user_update:
                            user_updated_count += 1
                
                result = {
                    "organizations": org_updated_count,
                    "users": user_updated_count
                }
                
                if org_updated_count > 0 or user_updated_count > 0:
                    logger.info(
                        f"[DisplayFieldSynchronizer] 同步完成, "
                        f"组织更新实例数: {org_updated_count}, "
                        f"用户更新实例数: {user_updated_count}"
                    )
                
                return result
        
        except Exception as e:
            logger.error(
                f"[DisplayFieldSynchronizer] 同步 _display 字段失败: {e}",
                exc_info=True
            )
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

def sync_display_fields_for_system_mgmt(
    organizations: List[Dict[str, Any]] = None,
    users: List[Dict[str, str]] = None
) -> Dict[str, Any]:
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
