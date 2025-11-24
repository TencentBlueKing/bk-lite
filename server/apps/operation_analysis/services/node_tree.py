# -- coding: utf-8 --
# @File: node_tree.py
# @Time: 2025/11/3 16:21
# @Author: windyzhao

class TreeNodeBuilder:
    """树节点构建器基类"""

    @staticmethod
    def get_directory_nodes(directories):
        """构建目录节点"""
        nodes = {}
        parent_children_map = {}

        for directory in directories:
            node_key = f"directory_{directory.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": directory.id,
                "desc": directory.desc,
                "name": directory.name,
                "type": "directory",
                "groups": directory.groups,
                "children": []
            }

            # 构建父子关系映射
            parent_key = f"directory_{directory.parent_id}" if directory.parent_id else None
            if parent_key not in parent_children_map:
                parent_children_map[parent_key] = []
            parent_children_map[parent_key].append(node_key)

        return nodes, parent_children_map

    @staticmethod
    def get_dashboard_nodes(dashboards, parent_children_map):
        """构建仪表盘节点"""
        nodes = {}

        for dashboard in dashboards:
            node_key = f"dashboard_{dashboard.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": dashboard.id,
                "name": dashboard.name,
                "desc": dashboard.desc,
                "type": "dashboard",
                "groups": dashboard.groups,
                "children": []
            }

            # 仪表盘属于目录的子节点
            parent_key = f"directory_{dashboard.directory_id}"
            if parent_key not in parent_children_map:
                parent_children_map[parent_key] = []
            parent_children_map[parent_key].append(node_key)

        return nodes

    @staticmethod
    def get_topology_nodes(topologies, parent_children_map):
        """构建拓扑图节点"""
        nodes = {}
        for topology in topologies:
            node_key = f"topology_{topology.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": topology.id,
                "name": topology.name,
                "desc": topology.desc,
                "type": "topology",
                "groups": topology.groups,
                "children": []
            }

            parent_key = f"directory_{topology.directory_id}"
            if parent_key not in parent_children_map:
                parent_children_map[parent_key] = []
            parent_children_map[parent_key].append(node_key)

        return nodes

    @staticmethod
    def get_architecture_nodes(architectures, parent_children_map):
        """构建架构图节点"""
        nodes = {}
        for architecture in architectures:
            node_key = f"architecture_{architecture.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": architecture.id,
                "name": architecture.name,
                "desc": architecture.desc,
                "type": "architecture",
                "groups": architecture.groups,
                "children": []
            }

            parent_key = f"directory_{architecture.directory_id}"
            if parent_key not in parent_children_map:
                parent_children_map[parent_key] = []
            parent_children_map[parent_key].append(node_key)

        return nodes
