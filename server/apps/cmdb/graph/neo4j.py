import os

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.graph import Path

from apps.cmdb.constants import INSTANCE
from apps.cmdb.graph.format_type import FORMAT_TYPE
from apps.core.exceptions.base_app_exception import BaseAppException

load_dotenv()


class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
        )
        self.session = None

    def close(self):
        """关闭连接"""
        if self.session:
            self.session.close()
        if self.driver:
            self.driver.close()

    def __enter__(self):
        self.session = self.driver.session()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def entity_to_list(self, data: iter):
        """将使用fetchall查询的结果转换成列表类型"""
        return [self.entity_to_dict(i) for i in data]

    def entity_to_dict(self, data: tuple):
        """将使用single查询的结果转换成字典类型"""
        return dict(_id=data[0].id, _label=list(data[0].labels)[0], **data[0]._properties)

    def edge_to_list(self, data: iter, return_entity: bool):
        """将使用fetchall查询的结果转换成列表类型"""
        result = [
            {
                "src": self.entity_to_dict((i[0].start_node,)),
                "edge": self.edge_to_dict((i[0].relationships[0],)),
                "dst": self.entity_to_dict((i[0].end_node,)),
            }
            for i in data
        ]
        return result if return_entity else [i["edge"] for i in result]

    def edge_to_dict(self, data: tuple):
        """将使用single查询的结果转换成字典类型"""
        return dict(_id=data[0].id, _label=data[0].type, **data[0]._properties)

    def format_properties(self, properties: dict):
        """将属性格式化为sql中的字符串格式"""
        properties_str = "{"
        for key, value in properties.items():
            if type(value) == str:
                properties_str += f"{key}:'{value}',"
            else:
                properties_str += f"{key}:{value},"
        properties_str = properties_str[:-1]
        properties_str += "}"
        return properties_str

    def create_entity(
            self,
            label: str,
            properties: dict,
            check_attr_map: dict,
            exist_items: list,
            operator: str = None,
    ):
        """
        快速创建一个实体
        """
        result = self._create_entity(label, properties, check_attr_map, exist_items, operator)
        return result

    @staticmethod
    def check_unique_attr(item, check_attr_map, exist_items, is_update=False):
        """校验唯一属性"""
        not_only_attr = set()

        check_attrs = [i for i in check_attr_map.keys() if i in item] if is_update else check_attr_map.keys()

        for exist_item in exist_items:
            for attr in check_attrs:
                if exist_item[attr] == item[attr]:
                    not_only_attr.add(attr)

        if not not_only_attr:
            return

        message = ""
        for attr in not_only_attr:
            message += f"{check_attr_map[attr]} exist；"

        raise BaseAppException(message)

    def check_required_attr(self, item, check_attr_map, is_update=False):
        """校验必填属性"""
        not_required_attr = set()

        check_attrs = [i for i in check_attr_map.keys() if i in item] if is_update else check_attr_map.keys()

        for attr in check_attrs:
            if not item.get(attr):
                not_required_attr.add(attr)

        if not not_required_attr:
            return

        message = ""
        for attr in not_required_attr:
            # 记录必填项目为空
            message += f"{check_attr_map[attr]} is empty；"

        raise BaseAppException(message)

    def get_editable_attr(self, item, check_attr_map):
        """取可编辑属性"""
        return {k: v for k, v in item.items() if k in check_attr_map}

    def _create_entity(
            self,
            label: str,
            properties: dict,
            check_attr_map: dict,
            exist_items: list,
            operator: str = None,
    ):
        # 校验必填项标签非空
        if not label:
            raise BaseAppException("label is empty")

        # 校验唯一属性
        self.check_unique_attr(properties, check_attr_map.get("is_only", {}), exist_items)

        # 校验必填项
        self.check_required_attr(properties, check_attr_map.get("is_required", {}))

        # 补充创建人
        if operator:
            properties.update(_creator=operator)

        # 创建实体
        properties_str = self.format_properties(properties)
        entity = self.session.run(f"CREATE (n:{label} {properties_str}) RETURN n").single()

        return self.entity_to_dict(entity)

    def create_edge(
            self,
            label: str,
            a_id: int,
            a_label: str,
            b_id: int,
            b_label: str,
            properties: dict,
            check_asst_key: str,
    ):
        """
        快速创建一条边
        """
        result = self._create_edge(label, a_id, a_label, b_id, b_label, properties, check_asst_key)
        return result

    def _create_edge(
            self,
            label: str,
            a_id: int,
            a_label: str,
            b_id: int,
            b_label: str,
            properties: dict,
            check_asst_key: str = "model_asst_id",
    ):
        # 校验必填项标签非空
        if not label:
            raise BaseAppException("label is empty")

        # 校验边是否已经存在
        check_asst_val = properties.get(check_asst_key)
        edge_count = self.session.run(
            f"MATCH (a:{a_label})-[e]-(b:{b_label}) WHERE id(a) = {a_id} AND id(b) = {b_id} AND e.{check_asst_key} = '{check_asst_val}' RETURN COUNT(e) AS count"
            # noqa
        ).single()["count"]
        if edge_count > 0:
            raise BaseAppException("edge already exists")

        # 创建边
        properties_str = self.format_properties(properties)
        edge = self.session.run(
            # f"MATCH (a:{a_label}), (b:{b_label}) WHERE id(a) = {a_id} AND id(b) = {b_id} CREATE (a)-[e:{label} {properties_str}]->(b) RETURN e"  # noqa
            f"MATCH (a:{a_label}) WHERE id(a) = {a_id} WITH a MATCH (b:{b_label}) WHERE id(b) = {b_id} CREATE (a)-[e:{label} {properties_str}]->(b) RETURN e"
            # noqa
        ).single()

        return self.edge_to_dict(edge)

    def batch_create_entity(
            self,
            label: str,
            properties_list: list,
            check_attr_map: dict,
            exist_items: list,
            operator: str = None,
    ):
        """批量创建实体"""
        results = []
        for index, properties in enumerate(properties_list):
            result = {}
            try:
                entity = self._create_entity(label, properties, check_attr_map, exist_items, operator)
                result.update(data=entity, success=True)
                exist_items.append(entity)
            except Exception as e:
                message = f"article {index + 1} data, {e}"
                result.update(message=message, success=False)
            results.append(result)
        return results

    def batch_create_edge(
            self,
            label: str,
            a_label: str,
            b_label: str,
            edge_list: list,
            check_asst_key: str,
    ):
        """批量创建边"""
        results = []
        for index, edge_info in enumerate(edge_list):
            result = {}
            try:
                a_id = edge_info["src_id"]
                b_id = edge_info["dst_id"]
                edge = self._create_edge(label, a_id, a_label, b_id, b_label, edge_info, check_asst_key)
                result.update(data=edge, success=True)
            except Exception as e:
                message = f"article {index + 1} data, {e}"
                result.update(message=message, success=False)
            results.append(result)
        return results

    def format_search_params(self, params: list, param_type: str = "AND"):
        """
        查询参数格式化:
        bool: {"field": "is_host", "type": "bool", "value": True} -> "n.is_host = True"

        time: {"field": "create_time", "type": "time", "start": "", "end": ""} -> "n.time >= '2022-01-01 08:00:00' AND n.time <= '2022-01-02 08:00:00'"     # noqa

        str=: {"field": "name", "type": "str=", "value": "host"} -> "n.name = 'host'"
        str<>: {"field": "name", "type": "str<>", "value": "host"} -> "n.name <> 'host'"
        str*: {"field": "name", "type": "str*", "value": "host"} -> "n.name =~ '.*host.*'"
        str[]: {"field": "name", "type": "str[]", "value": ["host"]} -> "n.name IN ["host"]"

        int=: {"field": "mem", "type": "int=", "value": 200} -> "n.mem = 200"
        int>: {"field": "mem", "type": "int>", "value": 200} -> "n.mem > 200"
        int<: {"field": "mem", "type": "int<", "value": 200} -> "n.mem < 200"
        int<>: {"field": "mem", "type": "int<>", "value": 200} -> "n.mem <> 200"
        int[]: {"field": "mem", "type": "int[]", "value": [200]} -> "n.mem IN [200]"

        id=: {"field": "id", "type": "id=", "value": 115} -> "n(id) = 115"
        id[]: {"field": "id", "type": "id[]", "value": [115,116]} -> "n(id) IN [115,116]"

        list[]: {"field": "test", "type": "list[]", "value": [1,2]} -> "ANY(x IN value WHERE x IN n.test)"
        """

        params_str = ""
        param_type = f" {param_type} "
        for param in params:
            method = FORMAT_TYPE.get(param["type"])
            if not method:
                continue

            params_str += method(param)
            params_str += param_type

        return f"({params_str[:-len(param_type)]})" if params_str else params_str

    def format_final_params(self, search_params: list, search_param_type: str = "AND", permission_params=""):
        search_params_str = self.format_search_params(search_params, search_param_type)

        if not search_params_str:
            return permission_params

        if not permission_params:
            return search_params_str

        return f"{search_params_str} AND {permission_params}"

    def query_entity(
            self,
            label: str,
            params: list,
            page: dict = None,
            order: str = None,
            order_type: str = "ASC",
            param_type="AND",
            permission_params: str = "",
    ):
        """
        查询实体
        """
        label_str = f":{label}" if label else ""
        params_str = self.format_final_params(params, search_param_type=param_type, permission_params=permission_params)
        params_str = f"WHERE {params_str}" if params_str else params_str

        sql_str = f"MATCH (n{label_str}) {params_str} RETURN n"

        # order by
        sql_str += f" ORDER BY n.{order} {order_type}" if order else f" ORDER BY ID(n) {order_type}"

        count_str = f"MATCH (n{label_str}) {params_str} RETURN COUNT(n) AS count"
        count = None
        if page:
            count = self.session.run(count_str).single()["count"]
            sql_str += f" SKIP {page['skip']} LIMIT {page['limit']}"

        objs = self.session.run(sql_str)
        return self.entity_to_list(objs), count

    def query_entity_by_id(self, id: int):
        """
        查询实体详情
        """
        obj = self.session.run(f"MATCH (n) WHERE id(n) = {id} RETURN n").single()
        if not obj:
            return {}
        return self.entity_to_dict(obj)

    def query_entity_by_ids(self, ids: list):
        """
        查询实体列表
        """
        objs = self.session.run(f"MATCH (n) WHERE id(n) IN {ids} RETURN n")
        if not objs:
            return []
        return self.entity_to_list(objs)

    def query_edge(
            self,
            label: str,
            params: list,
            param_type: str = "AND",
            return_entity: bool = False,
    ):
        """
        查询边
        """
        label_str = f":{label}" if label else ""
        params_str = self.format_search_params(params, param_type)
        params_str = f"WHERE {params_str}" if params_str else params_str

        objs = self.session.run(f"MATCH p=((a)-[n{label_str}]->(b)) {params_str} RETURN p")

        return self.edge_to_list(objs, return_entity)

    def query_edge_by_id(self, id: int, return_entity: bool = False):
        """
        查询边详情
        """
        objs = self.session.run(f"MATCH p=((a)-[n]->(b)) WHERE id(n) = {id} RETURN p")
        edges = self.edge_to_list(objs, return_entity)
        return edges[0]

    def format_properties_set(self, properties: dict):
        """格式化properties的set数据"""
        properties_str = ""
        for key, value in properties.items():
            if type(value) == str:
                properties_str += f"n.{key}='{value}',"
            else:
                properties_str += f"n.{key}={value},"
        return properties_str if properties_str == "" else properties_str[:-1]

    def set_entity_properties(
            self,
            label: str,
            entity_ids: list,
            properties: dict,
            check_attr_map: dict,
            exist_items: list,
            check: bool = True,
    ):
        """
        设置实体属性
        """
        if check:
            # 校验唯一属性
            self.check_unique_attr(
                properties,
                check_attr_map.get("is_only", {}),
                exist_items,
                is_update=True,
            )

            # 校验必填项
            self.check_required_attr(properties, check_attr_map.get("is_required", {}), is_update=True)

            # 取出可编辑属性
            properties = self.get_editable_attr(properties, check_attr_map.get("editable", {}))

        label_str = f":{label}" if label else ""
        properties_str = self.format_properties_set(properties)
        if not properties_str:
            raise BaseAppException("properties is empty")
        entitys = self.session.run(f"MATCH (n{label_str}) WHERE id(n) IN {entity_ids} SET {properties_str} RETURN n")
        return self.entity_to_list(entitys)

    def format_properties_remove(self, attrs: list):
        """格式化properties的remove数据"""
        properties_str = ""
        for attr in attrs:
            properties_str += f"n.{attr},"
        return properties_str if properties_str == "" else properties_str[:-1]

    def remove_entitys_properties(self, label: str, params: list, attrs: list):
        """移除某些实体的某些属性"""
        label_str = f":{label}" if label else ""
        properties_str = self.format_properties_remove(attrs)
        params_str = self.format_search_params(params)
        params_str = f"WHERE {params_str}" if params_str else params_str

        self.session.run(f"MATCH (n{label_str}) {params_str} REMOVE {properties_str} RETURN n")

    def batch_delete_entity(self, label: str, entity_ids: list):
        """批量删除实体"""
        label_str = f":{label}" if label else ""
        self.session.run(f"MATCH (n{label_str}) WHERE id(n) IN {entity_ids} DETACH DELETE n")

    def detach_delete_entity(self, label: str, id: int):
        """删除实体，以及实体的关联关系"""
        label_str = f":{label}" if label else ""
        self.session.run(f"MATCH (n{label_str}) WHERE id(n) = {id} DETACH DELETE n")

    def delete_edge(self, edge_id: int):
        """删除边"""
        self.session.run(f"MATCH ()-[n]->() WHERE id(n) = {edge_id} DELETE n")

    def entity_objs(self, label: str, params: list, permission_params: str = ""):
        """实体对象查询"""

        label_str = f":{label}" if label else ""
        params_str = self.format_final_params(params, permission_params=permission_params)
        params_str = f"WHERE {params_str}" if params_str else params_str

        sql_str = f"MATCH (n{label_str}) {params_str} RETURN n"

        inst_objs = self.session.run(sql_str)
        return inst_objs

    def query_topo(self, label: str, inst_id: int):
        """查询实例拓扑"""

        label_str = f":{label}" if label else ""
        params_str = self.format_search_params([{"field": "id", "type": "id=", "value": inst_id}])
        if params_str:
            params_str = f"AND {params_str}"
        src_objs = self.session.run(
            f"MATCH p=(n{label_str})-[*]->(m{label_str}) WHERE NOT (m)-->() {params_str} RETURN p"
        )
        dst_objs = self.session.run(
            f"MATCH p=(m{label_str})-[*]->(n{label_str}) WHERE NOT (m)<--() {params_str} RETURN p"
        )

        return dict(
            src_result=self.format_topo(inst_id, src_objs, True), dst_result=self.format_topo(inst_id, dst_objs, False)
        )

    def format_topo(self, start_id, objs, entity_is_src=True):
        """格式化拓扑数据"""

        if objs.peek() is None:
            return {}

        edge_map = {}
        entity_map = {}
        for obj in objs:
            for element in obj:
                if not isinstance(element, Path):
                    continue
                # 分离出路径中的点和线
                nodes = element.nodes  # 获取所有节点
                relationships = element.relationships  # 获取所有关系
                for node in nodes:
                    entity_map[node.id] = dict(_id=node.id, _label=list(node.labels)[0], **node._properties)
                for relationship in relationships:
                    edge_map[relationship.id] = dict(
                        _id=relationship.id, _label=relationship.type, **relationship._properties
                    )

        edges = list(edge_map.values())
        # 去除自己指向自己的边
        edges = [edge for edge in edges if edge["src_inst_id"] != edge["dst_inst_id"]]
        entities = list(entity_map.values())

        result = self.create_node(entity_map[start_id], edges, entities, entity_is_src)
        return result

    def create_node(self, entity, edges, entities, entity_is_src=True):
        """entity作为目标"""
        node = {
            "_id": entity["_id"],
            "model_id": entity["model_id"],
            "inst_name": entity["inst_name"],
            "children": [],
        }

        if entity_is_src:
            entity_key, child_entity_key = "src", "dst"
        else:
            entity_key, child_entity_key = "dst", "src"

        for edge in edges:
            if edge[f"{entity_key}_inst_id"] == entity["_id"]:
                child_entity = self.find_entity_by_id(edge[f"{child_entity_key}_inst_id"], entities)
                if child_entity:
                    child_node = self.create_node(child_entity, edges, entities, entity_is_src)
                    child_node["model_asst_id"] = edge["model_asst_id"]
                    child_node["asst_id"] = edge["asst_id"]
                    node["children"].append(child_node)
        return node

    def find_entity_by_id(self, entity_id, entities):
        """根据ID找实体"""
        for entity in entities:
            if entity["_id"] == entity_id:
                return entity
        return None

    def entity_count(self, label: str, group_by_attr: str, params: list, permission_params: str = ""):
        """实体数量"""

        label_str = f":{label}" if label else ""
        params_str = self.format_final_params(params, permission_params=permission_params)
        params_str = f"WHERE {params_str}" if params_str else params_str

        data = self.session.run(
            f"MATCH (n{label_str}) {params_str} RETURN n.{group_by_attr} AS {group_by_attr}, COUNT(n) AS count"
        )

        return {i[group_by_attr]: i["count"] for i in data}

    def full_text(self, search: str, permission_params: str = ""):
        """全文检索, 无实例权限"""

        params = f"{permission_params} AND" if permission_params else ""

        # query = f"""
        #         MATCH (n:{INSTANCE})
        #         WHERE {params} AND
        #             ANY(key IN keys(n) WHERE (NOT n[key] IS NULL AND toString(n[key]) CONTAINS '{search}'))
        #         RETURN n
        #         """

        query = f"""MATCH (n:{INSTANCE}) WHERE {params} ANY(key IN keys(n) WHERE (NOT n[key] IS NULL AND ANY(value IN n[key] WHERE toString(value) CONTAINS '{search}'))) RETURN n"""  # noqa
        objs = self.session.run(query)
        return self.entity_to_list(objs)
