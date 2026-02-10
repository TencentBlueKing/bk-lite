from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Group


class GroupUtils(object):
    @staticmethod
    def get_group_with_descendants(group_ids):
        """
        获取指定组织及其所有子孙组织的ID列表（内存递归，单次数据库查询）
        :param group_ids: 组织ID或组织ID列表
        :return: 包含自身及所有子孙组织的ID列表
        """
        if isinstance(group_ids, (int, str)):
            group_ids = [int(group_ids)]
        else:
            group_ids = [int(gid) for gid in group_ids]
        all_groups = Group.objects.values_list("id", "parent_id")
        children_map = {}
        for gid, pid in all_groups:
            if pid is not None:
                children_map.setdefault(pid, []).append(gid)

        def collect_descendants(gid, result_set):
            result_set.add(gid)
            for child_id in children_map.get(gid, []):
                collect_descendants(child_id, result_set)

        result = set()
        for gid in group_ids:
            collect_descendants(gid, result)
        return list(result)

    @staticmethod
    def get_group_with_descendants_filtered(group_ids, group_list=None):
        """
        获取指定组织及其所有子孙组织的ID列表，支持权限过滤（单次数据库查询）

        此方法是 get_group_with_descendants() 的增强版本，支持 group_list 权限过滤。
        用于替代存在 N+1 查询问题的 get_all_child_groups() 方法。

        :param group_ids: 组织ID或组织ID列表
        :param group_list: 用户有权限的组织ID列表，如果为None则不过滤
        :return: 包含自身及所有子孙组织的ID列表（已过滤权限）
        """
        if isinstance(group_ids, (int, str)):
            group_ids = [int(group_ids)]
        else:
            group_ids = [int(gid) for gid in group_ids]

        # 单次查询获取所有组织的父子关系
        all_groups = Group.objects.values_list("id", "parent_id")
        children_map = {}
        for gid, pid in all_groups:
            if pid is not None:
                children_map.setdefault(pid, []).append(gid)

        # 将 group_list 转换为 set 以提高查找效率
        allowed_set = None
        if group_list is not None:
            # group_list 可能是 [{"id": 1}, {"id": 2}] 或 [1, 2] 格式
            if group_list and isinstance(group_list[0], dict):
                allowed_set = {item["id"] for item in group_list}
            else:
                allowed_set = set(group_list)

        def collect_descendants(gid, result_set):
            # 如果有权限过滤，只添加有权限的组织
            if allowed_set is None or gid in allowed_set:
                result_set.add(gid)
            # 继续递归子组织（即使当前组织无权限，子组织可能有权限）
            for child_id in children_map.get(gid, []):
                collect_descendants(child_id, result_set)

        result = set()
        for gid in group_ids:
            collect_descendants(gid, result)
        return list(result)

    @staticmethod
    def get_all_child_groups(group_id, include_self=True, group_list=None):
        """
        递归获取指定组织的所有子组织ID（仅限用户有权限的组织）

        TODO: 此方法存在 N+1 查询问题，每层递归都会查询数据库。
              请使用 get_group_with_descendants() 或 get_group_with_descendants_filtered() 替代。

        :param group_id: 父组织ID
        :param include_self: 是否包含自身
        :param group_list: 用户有权限的组织ID列表，如果为None则不过滤
        :return: 组织ID列表
        """
        group_ids = set()
        if include_self:
            group_ids.add(group_id)

        # 获取直接子组织
        child_groups = Group.objects.filter(parent_id=group_id).values_list("id", flat=True)

        # 如果提供了 group_list，只保留用户有权限的子组织
        if group_list is not None:
            child_groups = [cid for cid in child_groups if cid in group_list]

        # 递归获取子组织的子组织
        for child_id in child_groups:
            group_ids.update(GroupUtils.get_all_child_groups(child_id, include_self=True, group_list=group_list))

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

        # 包含子组织：获取所有子组织（仅限用户有权限的）
        # 使用优化后的单次查询方法替代 N+1 的 get_all_child_groups
        authorized_groups = GroupUtils.get_group_with_descendants_filtered(target_group_id, group_list=user_group_list)

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
        :return: 根节点列表（按ID正序排序）
        """
        root_groups = []

        for group_id, group_data in group_dict.items():
            if "parentId" in group_data and group_data["parentId"] in group_dict:
                parent_id = group_data["parentId"]
                group_dict[parent_id]["subGroups"].append(group_data)
                group_dict[parent_id]["subGroupCount"] += 1
            else:
                root_groups.append(group_data)

        # 对根节点按ID正序排序
        root_groups.sort(key=lambda x: x["id"])

        # 递归对所有子节点按ID正序排序
        def sort_subgroups(groups):
            for group in groups:
                if group["subGroups"]:
                    group["subGroups"].sort(key=lambda x: x["id"])
                    sort_subgroups(group["subGroups"])

        sort_subgroups(root_groups)

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

    @staticmethod
    def build_group_paths(groups, user_groups):
        """
        构建用户组的父级路径格式
        例如：用户在 tree1 组，父级链为 Default -> tree1，则返回 "Default/tree1"

        :param groups: 组查询集（需包含用户所在组及其所有父级组）
        :param user_groups: 用户所属的组ID列表
        :return: 组路径字符串列表，例如 ["Default/tree1", "Default/tree2"]
        """
        # 构建组字典，便于查找
        group_dict = {}
        for group in groups:
            group_dict[group.id] = {
                "id": group.id,
                "name": group.name,
                "parent_id": getattr(group, "parent_id", None),
            }

        # 递归获取从根到当前组的完整路径
        def get_path_from_root(group_id):
            """获取从根组织到当前组织的完整路径"""
            path_parts = []
            current_id = group_id

            while current_id and current_id in group_dict:
                current_group = group_dict[current_id]
                path_parts.insert(0, current_group["name"])  # 插入到开头，保持从根到叶的顺序
                current_id = current_group["parent_id"]

            return "/".join(path_parts)

        # 为用户所在的每个组构建路径信息
        group_paths = []
        for group_id in user_groups:
            if group_id in group_dict:
                path = get_path_from_root(group_id)
                group_paths.append(path)

        logger.info(f"构建组路径完成，用户组数量: {len(user_groups)}, 路径数量: {len(group_paths)}")
        return group_paths
