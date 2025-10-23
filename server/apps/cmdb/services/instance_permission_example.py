# -*- coding: utf-8 -*-
"""
实例权限重构示例
展示如何使用 FalkorDBClient 的新权限方法来简化 InstanceManage 中的权限逻辑
"""

from apps.cmdb.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.instance import InstanceManage


class InstanceManageWithPermission:
    """
    使用新的权限抽象方法的实例管理示例
    """

    @staticmethod
    def instance_list_with_permission(teams: list, inst_names: list, creator: str, 
                                    model_id: str, search_params: list, 
                                    page: int, page_size: int, order: str = None):
        """
        使用新权限方法的实例列表查询
        
        Args:
            teams: 用户所在的团队列表
            inst_names: 特殊授权的实例名称列表
            creator: 创建人用户名
            model_id: 模型ID
            search_params: 搜索参数列表 (原来的 query_list)
            page: 页码
            page_size: 每页大小
            order: 排序字段
            
        Returns:
            tuple: (实例列表, 总数)
        """
        _page = dict(skip=(page - 1) * page_size, limit=page_size)
        
        # 处理排序
        order_type = "ASC"
        if order and order.startswith("-"):
            order = order.replace('-', '')
            order_type = "DESC"
        
        with GraphClient() as ag:
            # 使用新的统一权限查询方法
            inst_list, count = ag.query_entity_with_permission(
                label=INSTANCE,
                teams=teams,
                inst_names=inst_names,
                creator=creator,
                model_id=model_id,
                search_params=search_params,
                page=_page,
                order=order,
                order_type=order_type
            )
        
        return inst_list, count

    @staticmethod
    def export_instances_with_permission(teams: list, inst_names: list, creator: str,
                                       model_id: str, inst_ids: list = None,
                                       search_params: list = None):
        """
        使用新权限方法的实例导出
        
        Args:
            teams: 用户所在的团队列表
            inst_names: 特殊授权的实例名称列表
            creator: 创建人用户名
            model_id: 模型ID
            inst_ids: 要导出的实例ID列表
            search_params: 额外的搜索参数
            
        Returns:
            list: 符合权限的实例列表
        """
        with GraphClient() as ag:
            # 使用新的导出权限方法
            instances = ag.export_entities_with_permission(
                label=INSTANCE,
                teams=teams,
                inst_names=inst_names,
                creator=creator,
                model_id=model_id,
                inst_ids=inst_ids,
                search_params=search_params
            )
        
        return instances

    @staticmethod
    def model_instance_count_with_permission(teams: list, inst_names: list, creator: str,
                                           search_params: list = None):
        """
        使用新权限方法的模型实例统计
        
        Args:
            teams: 用户所在的团队列表
            inst_names: 特殊授权的实例名称列表 (跨模型)
            creator: 创建人用户名
            search_params: 额外的搜索参数
            
        Returns:
            list: 按模型ID分组的统计结果
        """
        with GraphClient() as ag:
            # 使用新的统计权限方法
            counts = ag.count_entity_with_permission(
                label=INSTANCE,
                group_by_attr="model_id",
                teams=teams,
                inst_names=inst_names,
                creator=creator,
                search_params=search_params
            )
        
        return counts

    @staticmethod
    def fulltext_search_with_permission(search_keyword: str, teams: list, 
                                      inst_names: list, creator: str,
                                      search_params: list = None):
        """
        使用新权限方法的全文检索
        
        Args:
            search_keyword: 搜索关键词
            teams: 用户所在的团队列表
            inst_names: 特殊授权的实例名称列表
            creator: 创建人用户名
            search_params: 额外的搜索参数
            
        Returns:
            list: 搜索结果
        """
        with GraphClient() as ag:
            # 使用新的全文检索权限方法
            results = ag.fulltext_search_with_permission(
                search=search_keyword,
                teams=teams,
                inst_names=inst_names,
                creator=creator,
                search_params=search_params
            )
        
        return results


# 示例：如何在视图中使用新的权限方法
class InstanceViewExample:
    """
    展示如何在视图中使用新的权限方法
    """
    
    def search_example(self, request):
        """
        搜索实例的示例 - 替代原来的 search 方法
        """
        # 从请求中获取参数
        model_id = request.data['model_id']
        page = int(request.data.get("page", 1))
        page_size = int(request.data.get("page_size", 10))
        order = request.data.get("order", "")
        query_list = request.data.get("query_list", [])
        
        # 获取权限信息 (这些应该从权限系统获取)
        current_team = request.COOKIES.get("current_team")
        teams = [current_team] if current_team else []
        inst_names = []  # 从权限系统获取用户有权限的实例名称列表
        creator = request.user.username
        
        # 使用新的权限方法查询
        instance_list, count = InstanceManageWithPermission.instance_list_with_permission(
            teams=teams,
            inst_names=inst_names,
            creator=creator,
            model_id=model_id,
            search_params=query_list,
            page=page,
            page_size=page_size,
            order=order
        )
        
        return {"insts": instance_list, "count": count}
    
    def export_example(self, request, model_id):
        """
        导出实例的示例 - 替代原来的 inst_export 方法
        """
        # 获取权限信息
        current_team = request.COOKIES.get("current_team")
        teams = [current_team] if current_team else []
        inst_names = []  # 从权限系统获取
        creator = request.user.username
        
        # 获取要导出的实例ID
        inst_ids = request.data.get("inst_ids", [])
        
        # 使用新的权限方法导出
        instances = InstanceManageWithPermission.export_instances_with_permission(
            teams=teams,
            inst_names=inst_names,
            creator=creator,
            model_id=model_id,
            inst_ids=inst_ids
        )
        
        return instances


# 权限参数构建工具
class PermissionParamsBuilder:
    """
    权限参数构建工具，用于从现有的权限系统中提取参数
    """
    
    @staticmethod
    def build_from_permission_rules(permission_rules: dict, current_team: str, username: str):
        """
        从权限规则构建新权限方法需要的参数
        
        Args:
            permission_rules: 从 get_permission_rules 获取的权限规则
            current_team: 当前团队ID
            username: 用户名
            
        Returns:
            dict: 包含 teams, inst_names, creator 的字典
        """
        # 1. 团队权限
        teams = permission_rules.get("team", [])
        if current_team and current_team not in teams:
            teams.append(current_team)
        
        # 2. 实例权限
        rules = permission_rules.get("instance", [])
        from apps.cmdb.utils.permisssion_util import CmdbRulesFormatUtil
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        inst_names = list(permission_instances_map.keys())
        
        # 3. 创建人
        creator = username
        
        return {
            "teams": teams,
            "inst_names": inst_names,
            "creator": creator
        }

    @staticmethod
    def build_from_legacy_params(user_groups: list, roles: list, inst_names: list, creator: str):
        """
        从旧的参数格式构建新权限方法需要的参数
        
        Args:
            user_groups: 用户组列表
            roles: 角色列表  
            inst_names: 实例名称列表
            creator: 创建人
            
        Returns:
            dict: 包含 teams, inst_names, creator 的字典
        """
        # 将 user_groups 转换为 teams (可能需要根据实际数据结构调整)
        teams = user_groups if isinstance(user_groups, list) else [user_groups]
        
        return {
            "teams": teams,
            "inst_names": inst_names or [],
            "creator": creator
        }


# 使用示例和对比
def usage_comparison():
    """
    使用示例和新旧方法对比
    """
    
    # === 旧方法示例 ===
    def old_way():
        # 复杂的权限逻辑分散在各个方法中
        user_groups = [1, 2, 3]
        roles = ["admin"]
        model_id = "host"
        params = [{"field": "ip", "type": "str*", "value": "192.168"}]
        inst_names = ["host1", "host2"]
        creator = "admin"
        
        # 需要手动构建复杂的权限参数
        permission_params = InstanceManage.get_permission_params(user_groups, roles)
        permission_or_creator_filter = {
            "inst_names": inst_names,
            "creator": creator
        }
        
        with GraphClient() as ag:
            # 使用复杂的原始方法
            inst_list, count = ag.query_entity(
                INSTANCE,
                params,
                permission_params=permission_params,
                permission_or_creator_filter=permission_or_creator_filter,
            )
    
    # === 新方法示例 ===
    def new_way():
        # 统一的权限逻辑，参数更清晰
        teams = [1, 2, 3]
        model_id = "host"
        search_params = [{"field": "ip", "type": "str*", "value": "192.168"}]
        inst_names = ["host1", "host2"]
        creator = "admin"
        
        with GraphClient() as ag:
            # 使用简洁的新方法
            inst_list, count = ag.query_entity_with_permission(
                label=INSTANCE,
                teams=teams,
                inst_names=inst_names,
                creator=creator,
                model_id=model_id,
                search_params=search_params,
                page={"skip": 0, "limit": 10}
            )
    
    print("权限逻辑已经抽象到 FalkorDBClient 中，使用更简洁！")


if __name__ == "__main__":
    usage_comparison()
