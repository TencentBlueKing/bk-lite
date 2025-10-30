from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Group


class GroupUtils(object):
    @staticmethod
    def get_all_child_groups(group_id, include_self=True):
        """
        递归获取指定组织的所有子组织ID
        :param group_id: 父组织ID
        :param include_self: 是否包含自身
        :return: 组织ID列表
        """
        group_ids = set()
        if include_self:
            group_ids.add(group_id)

        # 获取直接子组织
        child_groups = Group.objects.filter(parent_id=group_id).values_list("id", flat=True)

        # 递归获取子组织的子组织
        for child_id in child_groups:
            group_ids.update(GroupUtils.get_all_child_groups(child_id, include_self=True))

        return list(group_ids)

    @staticmethod
    def get_user_authorized_child_groups(user_group_list, target_group_id, include_children=False):
        """
        获取用户有权限的组织列表（支持级联查询）
        :param user_group_list: 用户所属的组织ID列表
        :param target_group_id: 目标组织ID（从cookies中获取的current_team）
        :param include_children: 是否包含子组织
        :return: 最终的组织ID列表，用于数据查询
        """
        # 如果目标组织不在用户权限列表中，返回空
        if target_group_id not in user_group_list:
            return []

        # 不包含子组织，仅返回当前组织
        if not include_children:
            return [target_group_id]

        # 包含子组织：获取所有子组织
        all_child_groups = GroupUtils.get_all_child_groups(target_group_id, include_self=True)

        # 过滤出用户有权限的子组织（交集）
        authorized_groups = list(set(all_child_groups) & set(user_group_list))

        logger.info(f"用户组织列表: {user_group_list}, 目标组织: {target_group_id}, " f"包含子组织: {include_children}, 最终查询组织: {authorized_groups}")

        return authorized_groups

    @staticmethod
    def build_group_tree(groups, is_superuser=False, user_groups=None):
        """构建组的树状结构，只展示用户有权限的组及其父级组"""
        if user_groups is None:
            user_groups = []

        # 构建组字典（包含角色信息）
        group_dict = GroupUtils._build_group_dict(groups, is_superuser, user_groups)

        # 超级用户返回完整树结构
        if is_superuser:
            return GroupUtils._assemble_tree(group_dict)

        # 普通用户：获取需要展示的组ID集合（有权限的组及其所有父级）
        visible_group_ids = GroupUtils._get_visible_groups(group_dict, user_groups)

        # 构建过滤后的树结构
        return GroupUtils._build_filtered_tree(group_dict, visible_group_ids, user_groups)

    @staticmethod
    def _build_group_dict(groups, is_superuser=False, user_groups=None):
        """
        统一的组字典构建方法，包含角色信息
        :param groups: 组查询集
        :param is_superuser: 是否超级用户
        :param user_groups: 用户组列表
        :return: 组字典
        """
        if user_groups is None:
            user_groups = []

        group_dict = {}

        for group in groups:
            # 使用预加载的 roles 数据，避免 N+1 查询
            role_ids = [role.id for role in group.roles.all()]

            group_dict[group.id] = {
                "id": group.id,
                "name": group.name,
                "subGroupCount": 0,
                "subGroups": [],
                "hasAuth": is_superuser or group.id in user_groups,
                "role_ids": role_ids,
                "is_virtual": group.is_virtual,
            }

            if hasattr(group, "parent_id") and group.parent_id:
                group_dict[group.id]["parentId"] = group.parent_id

        return group_dict

    @staticmethod
    def _assemble_tree(group_dict):
        """
        将组字典组装成树结构
        :param group_dict: 组字典
        :return: 根节点列表
        """
        root_groups = []

        for group_id, group_data in group_dict.items():
            if "parentId" in group_data and group_data["parentId"] in group_dict:
                parent_id = group_data["parentId"]
                group_dict[parent_id]["subGroups"].append(group_data)
                group_dict[parent_id]["subGroupCount"] += 1
            else:
                root_groups.append(group_data)

        return root_groups

    @staticmethod
    def _get_visible_groups(group_dict, user_groups):
        """递归获取需要展示的组ID集合"""
        visible_ids = set(user_groups)

        # 递归向上查找父级组
        def add_parent_groups(group_id):
            if group_id in group_dict and "parentId" in group_dict[group_id]:
                parent_id = group_dict[group_id]["parentId"]
                if parent_id not in visible_ids:
                    visible_ids.add(parent_id)
                    add_parent_groups(parent_id)

        for group_id in user_groups:
            add_parent_groups(group_id)

        logger.info(f"可见组数量: {len(visible_ids)}, 用户权限组: {len(user_groups)}")
        return visible_ids

    @staticmethod
    def _build_filtered_tree(group_dict, visible_group_ids, user_groups):
        """构建过滤后的树结构"""
        filtered_dict = {}

        # 创建过滤后的组字典
        for group_id in visible_group_ids:
            if group_id in group_dict:
                group_data = group_dict[group_id].copy()
                group_data["hasAuth"] = group_id in user_groups
                group_data["subGroups"] = []
                group_data["subGroupCount"] = 0
                filtered_dict[group_id] = group_data

        # 使用统一的树组装方法
        return GroupUtils._assemble_tree(filtered_dict)
