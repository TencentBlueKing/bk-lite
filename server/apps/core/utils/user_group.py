from apps.core.logger import logger
from apps.rpc.system_mgmt import SystemMgmt


def normalize_user_group_ids(group_list):
    """兼容 dict/int/str 结构并统一提取组织 ID 列表。"""
    normalized_group_ids = []
    for group in group_list or []:
        group_id = group.get("id") if isinstance(group, dict) else group
        try:
            normalized_group_ids.append(int(group_id))
        except (TypeError, ValueError):
            continue
    return normalized_group_ids


class SubGroup:
    def __init__(self, group_id, group_list):
        self.group_id = group_id
        self.group_list = group_list or []

    def get_group_id_and_subgroup_id(self):
        """获取组织ID与子组ID的列表"""
        if not self.group_list:
            return [self.group_id]

        sub_group = None
        for group in self.group_list:
            try:
                sub_group = self.get_subgroup(group, self.group_id)
                if sub_group:
                    break
            except Exception as e:
                logger.error(f"搜索组织时发生错误: {e}")
                continue

        group_id_list = [self.group_id]

        if not sub_group:
            return group_id_list

        try:
            subgroups = sub_group.get("subGroups", [])
            self.get_all_group_id_by_subgroups(subgroups, group_id_list)
        except Exception as e:
            logger.error(f"获取子组ID时发生错误: {e}")

        return group_id_list

    def get_subgroup(self, group, target_id):
        """根据子组ID获取子组"""
        if not isinstance(group, dict):
            return None

        if group.get("id") == target_id:
            return group

        subgroups = group.get("subGroups", [])
        if not isinstance(subgroups, list):
            return None

        for subgroup in subgroups:
            if not isinstance(subgroup, dict):
                continue

            if subgroup.get("id") == target_id:
                return subgroup

            nested_subgroups = subgroup.get("subGroups", [])
            if nested_subgroups:
                result = self.get_subgroup(subgroup, target_id)
                if result:
                    return result

        return None

    def get_all_group_id_by_subgroups(self, subgroups, id_list):
        """取出所有子组ID"""
        if not isinstance(subgroups, list):
            return

        for subgroup in subgroups:
            if not isinstance(subgroup, dict):
                continue

            subgroup_id = subgroup.get("id")
            if subgroup_id is not None:
                id_list.append(subgroup_id)

            nested_subgroups = subgroup.get("subGroups", [])
            if nested_subgroups:
                self.get_all_group_id_by_subgroups(nested_subgroups, id_list)


class Group:
    def __init__(self):
        self.system_mgmt_client = SystemMgmt()

    def get_group_list(self):
        """获取组织列表"""
        try:
            groups = self.system_mgmt_client.get_all_groups()
            if not groups:
                return []

            group_data = groups.get("data", [])
            return group_data if isinstance(group_data, list) else []

        except Exception as e:
            logger.error(f"获取组织列表时发生错误: {e}")
            return []

    def get_user_group_and_subgroup_ids(self, user_group_list=None):
        """获取用户组织ID与子组ID的列表"""
        if user_group_list is None:
            user_group_list = []

        normalized_group_ids = normalize_user_group_ids(user_group_list)
        if normalized_group_ids and len(normalized_group_ids) == len(user_group_list):
            return list(set(normalized_group_ids))

        all_groups = self.get_group_list()
        if not all_groups:
            return []

        user_group_and_subgroup_ids = []

        for group_info in user_group_list:
            if not isinstance(group_info, dict):
                continue

            group_id = group_info.get("id")
            if group_id is None:
                continue

            try:
                sub_group_processor = SubGroup(group_id, all_groups)
                group_ids = sub_group_processor.get_group_id_and_subgroup_id()
                user_group_and_subgroup_ids.extend(group_ids)
            except Exception as e:
                logger.error(f"处理组织ID {group_id} 时发生错误: {e}")
                continue

        return list(set(user_group_and_subgroup_ids))
