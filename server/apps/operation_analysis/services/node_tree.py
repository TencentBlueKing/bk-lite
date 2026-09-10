# -- coding: utf-8 --
# @File: node_tree.py
# @Time: 2025/11/3 16:21
# @Author: windyzhao


class TreeNodeBuilder:
    """树节点构建器基类"""

    @staticmethod
    def get_directory_nodes(directories, language=None):
        """构建目录节点"""
        from apps.operation_analysis.services.builtin_i18n import overlay_directory_payload

        nodes = {}
        parent_children_map = {}

        for directory in directories:
            payload = {"name": directory.name, "desc": directory.desc}
            overlay_directory_payload(payload, directory, language)
            node_key = f"directory_{directory.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": directory.id,
                "desc": payload["desc"],
                "name": payload["name"],
                "type": "directory",
                "groups": directory.groups,
                "is_build_in": directory.is_build_in,
                "_sort_created_at": directory.created_at,
                "_sort_id": directory.id,
                "children": [],
            }

            # 构建父子关系映射
            parent_key = f"directory_{directory.parent_id}" if directory.parent_id else None
            if parent_key not in parent_children_map:
                parent_children_map[parent_key] = []
            parent_children_map[parent_key].append(node_key)

        return nodes, parent_children_map

    @staticmethod
    def get_dashboard_nodes(dashboards, parent_children_map, language=None):
        """构建仪表盘节点"""
        return TreeNodeBuilder.get_canvas_nodes(dashboards, parent_children_map, "dashboard", language=language)

    @staticmethod
    def get_topology_nodes(topologies, parent_children_map, language=None):
        """构建拓扑图节点"""
        return TreeNodeBuilder.get_canvas_nodes(topologies, parent_children_map, "topology", language=language)

    @staticmethod
    def get_architecture_nodes(architectures, parent_children_map, language=None):
        """构建架构图节点"""
        return TreeNodeBuilder.get_canvas_nodes(architectures, parent_children_map, "architecture", language=language)

    @staticmethod
    def get_canvas_nodes(instances, parent_children_map, object_type, language=None):
        """构建通用画布节点"""
        from apps.operation_analysis.services.builtin_i18n import overlay_canvas_payload

        nodes = {}
        for instance in instances:
            payload = {"name": instance.name, "desc": instance.desc}
            overlay_canvas_payload(payload, instance, language)
            node_key = f"{object_type}_{instance.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": instance.id,
                "name": payload["name"],
                "desc": payload["desc"],
                "type": object_type,
                "groups": instance.groups,
                "is_build_in": instance.is_build_in,
                "_sort_created_at": instance.created_at,
                "_sort_id": instance.id,
                "children": [],
            }

            parent_key = f"directory_{instance.directory_id}"
            if parent_key not in parent_children_map:
                parent_children_map[parent_key] = []
            parent_children_map[parent_key].append(node_key)

        return nodes
