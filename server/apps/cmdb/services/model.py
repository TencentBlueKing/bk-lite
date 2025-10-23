import json

from apps.cmdb.constants import (
    CLASSIFICATION,
    CREATE_MODEL_CHECK_ATTR,
    INST_NAME_INFOS,
    INSTANCE,
    MODEL,
    MODEL_ASSOCIATION,
    ORGANIZATION,
    SUBORDINATE_MODEL,
    UPDATE_MODEL_CHECK_ATTR_MAP,
    USER,
    OPERATOR_MODEL,
)
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.language.service import SettingLanguage
from apps.cmdb.models import UPDATE_INST, DELETE_INST, CREATE_INST
from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.utils.change_record import create_change_record
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.services.user_group import UserGroup
from apps.rpc.system_mgmt import SystemMgmt


class ModelManage(object):
    @staticmethod
    def create_model(data: dict, username="admin"):
        """
        创建模型
        """
        # 对模型初始化默认属性实例名称
        data.update(attrs=json.dumps(INST_NAME_INFOS))

        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(MODEL, [])
            result = ag.create_entity(MODEL, data, CREATE_MODEL_CHECK_ATTR, exist_items)
            classification_info = ClassificationManage.search_model_classification_info(data["classification_id"])
            _ = ag.create_edge(
                SUBORDINATE_MODEL,
                classification_info["_id"],
                CLASSIFICATION,
                result["_id"],
                MODEL,
                dict(
                    classification_model_asst_id=f"{result['classification_id']}_{SUBORDINATE_MODEL}_{result['model_id']}"
                    # noqa
                ),
                "classification_model_asst_id",
            )
        create_change_record(operator=username, model_id=data["model_id"], label="模型管理",
                             _type=CREATE_INST, message=f"创建模型. 模型名称: {data['model_name']}",
                             inst_id=result['_id'], model_object=OPERATOR_MODEL)
        return result

    @staticmethod
    def delete_model(id: int):
        """
        删除模型
        """
        with GraphClient() as ag:
            ag.batch_delete_entity(MODEL, [id])

    @staticmethod
    def update_model(id: int, data: dict):
        """
        更新模型
        TODO 不能单独更新一个字段，如只更新icon，传递全部字段会导致其他字段校验不通过 model_name 后续考虑优化
        """
        model_id = data.pop("model_id", "")  # 不能更新model_id
        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(MODEL, [{"field": "model_id", "type": "str<>", "value": model_id}])
            # 排除当前正在更新的模型，避免自己和自己比较
            exist_items = [i for i in exist_items if i["_id"] != id]
            model = ag.set_entity_properties(MODEL, [id], data, UPDATE_MODEL_CHECK_ATTR_MAP, exist_items)
        return model[0]

    @staticmethod
    def search_model(language: str = "en", order_type: str = "ASC", order: str = "id",
                     classification_ids: list = [], model_list: list = [], group_list: list = []):
        """
        查询模型
        Args:
            language: 语言，默认英语
            order_type: 排序方式，asc升序/desc降序
            order: 排序字段，默认order_id
            classification_ids: 分类ID列表，可选，用于过滤特定分类下的模型
            model_list: 模型ID列表，可选，用于过滤特定模型
            group_list: 组织ID列表，可选，用于过滤特定组织下的模型
        """

        query_conditions = []

        # 构造过滤条件 - classification_ids 和 model_list 是"或"关系
        if classification_ids or model_list:
            or_conditions = []

            if classification_ids:
                for classification_id in classification_ids:
                    or_conditions.append({"field": "classification_id", "type": "str=", "value": classification_id})

            if model_list:
                for model_id in model_list:
                    or_conditions.append({"field": "model_id", "type": "str=", "value": model_id})

            query_conditions = or_conditions

        # 如果有group_id，添加组织过滤条件
        if group_list:
            query_conditions.append({"field": "group", "type": "list[]", "value": group_list})

        with GraphClient() as ag:
            # 如果有过滤条件，使用OR查询，否则查询所有
            if query_conditions:
                models, _ = ag.query_entity(MODEL, query_conditions, order=order, order_type=order_type,
                                            param_type="OR")
            else:
                models, _ = ag.query_entity(MODEL, [], order=order, order_type=order_type)

        lan = SettingLanguage(language)

        for model in models:
            model["model_name"] = lan.get_val("MODEL", model["model_id"]) or model["model_name"]
            # 确保所有模型都有order_id
            if "order_id" not in model:
                model["order_id"] = 0

        return models

    @staticmethod
    def _filter_models_by_permission(models: list, user, current_team: str, app_name: str):
        """
        根据权限过滤模型列表
        权限规则：
        1. 模型所在组织为default，都可以查询
        2. 用户所在组织和模型所在组织一样，可以查询和操作
        3. 被单独授予实例权限的模型
        """
        from apps.cmdb.utils.base import get_default_group_id
        from apps.core.utils.permission_utils import get_permission_rules
        from apps.cmdb.utils.permisssion_util import CmdbRulesFormatUtil
        from apps.cmdb.constants import PERMISSION_MODEL
        
        if not models:
            return []
            
        # 获取默认组织ID
        default_group_ids = get_default_group_id()
        default_group_id = default_group_ids[0] if default_group_ids else None
        current_team_id = int(current_team) if current_team else None
        
        # 获取用户的权限规则
        _permission_rules = get_permission_rules(user=user,
                                                 current_team=current_team, 
                                                 app_name=app_name,
                                                 permission_key=PERMISSION_MODEL)
        rules = _permission_rules.get("instance", [])
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        
        # 从权限规则中获取有权限的模型ID列表
        authorized_model_ids = set()
        for model_id, permissions in permission_instances_map.items():
            if permissions:  # 如果有任何权限
                authorized_model_ids.add(model_id)
        
        filtered_models = []
        
        for model in models:
            model_groups = model.get("group", [])
            model_id = model.get("model_id")
            
            # 权限判断逻辑
            has_permission = False
            
            # 1. 模型所在组织为default，都可以查询
            if default_group_id and default_group_id in model_groups:
                has_permission = True
            
            # 2. 用户所在组织和模型所在组织一样，可以查询和操作
            elif current_team_id and current_team_id in model_groups:
                has_permission = True
            
            # 3. 被单独授予实例权限的模型
            elif model_id in authorized_model_ids:
                has_permission = True
            
            if has_permission:
                filtered_models.append(model)
        
        return filtered_models

    @staticmethod
    def parse_attrs(attrs: str):
        return json.loads(attrs.replace('\\"', '"'))

    @staticmethod
    def create_model_attr(model_id, attr_info, username="admin"):
        """
        创建模型属性
        """
        with GraphClient() as ag:
            model_query = {"field": "model_id", "type": "str=", "value": model_id}
            models, model_count = ag.query_entity(MODEL, [model_query])
            if model_count == 0:
                raise BaseAppException("model not present")
            model_info = models[0]
            attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
            if attr_info["attr_id"] in {i["attr_id"] for i in attrs}:
                raise BaseAppException("model attr repetition")
            attrs.append(attr_info)
            result = ag.set_entity_properties(MODEL, [model_info["_id"]], dict(attrs=json.dumps(attrs)), {}, [], False)

        attrs = ModelManage.parse_attrs(result[0].get("attrs", "[]"))

        attr = None
        for attr in attrs:
            if attr["attr_id"] != attr_info["attr_id"]:
                continue
            attr = attr

        create_change_record(operator=username, model_id=model_id, label="模型管理",
                             _type=CREATE_INST, message=f"创建模型属性. 模型名称: {model_info['model_name']}",
                             inst_id=model_info['_id'], model_object=OPERATOR_MODEL)

        return attr

    @staticmethod
    def update_model_attr(model_id, attr_info, username="admin"):
        """
        更新模型属性
        """
        with GraphClient() as ag:
            model_query = {"field": "model_id", "type": "str=", "value": model_id}
            models, model_count = ag.query_entity(MODEL, [model_query])
            if model_count == 0:
                raise BaseAppException("model not present")
            model_info = models[0]
            attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
            if attr_info["attr_id"] not in {i["attr_id"] for i in attrs}:
                raise BaseAppException("model attr not present")
            for attr in attrs:
                if attr_info["attr_id"] != attr["attr_id"]:
                    continue
                attr.update(
                    attr_group=attr_info["attr_group"],
                    attr_name=attr_info["attr_name"],
                    is_required=attr_info["is_required"],
                    editable=attr_info["editable"],
                    option=attr_info["option"],
                )

            result = ag.set_entity_properties(MODEL, [model_info["_id"]], dict(attrs=json.dumps(attrs)), {}, [], False)

        attrs = ModelManage.parse_attrs(result[0].get("attrs", "[]"))

        attr = None
        for attr in attrs:
            if attr["attr_id"] != attr_info["attr_id"]:
                continue
            attr = attr

        create_change_record(operator=username, model_id=model_id, label="模型管理",
                             _type=UPDATE_INST, message=f"修改模型属性. 模型名称: {model_info['model_name']}",
                             inst_id=model_info['_id'], model_object=OPERATOR_MODEL)

        return attr

    @staticmethod
    def delete_model_attr(model_id: str, attr_id: str, username: str = "admin"):
        """
        删除模型属性
        """
        with GraphClient() as ag:
            model_query = {"field": "model_id", "type": "str=", "value": model_id}
            models, model_count = ag.query_entity(MODEL, [model_query])
            if model_count == 0:
                raise BaseAppException("model not present")
            model_info = models[0]
            attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
            new_attrs = [attr for attr in attrs if attr["attr_id"] != attr_id]
            result = ag.set_entity_properties(
                MODEL,
                [model_info["_id"]],
                dict(attrs=json.dumps(new_attrs)),
                {},
                [],
                False,
            )

            # 模型属性删除后，要删除对应模型实例的属性
            model_params = [{"field": "model_id", "type": "str=", "value": model_id}]
            ag.remove_entitys_properties(INSTANCE, model_params, [attr_id])

        create_change_record(operator=username, model_id=model_id, label="模型管理",
                             _type=DELETE_INST, message=f"删除模型属性. 模型名称: {model_info['model_name']}",
                             inst_id=model_info['_id'], model_object=OPERATOR_MODEL)

        return ModelManage.parse_attrs(result[0].get("attrs", "[]"))

    @staticmethod
    def search_model_info(model_id: str):
        """
        查询模型详情
        """
        query_data = {"field": "model_id", "type": "str=", "value": model_id}
        with GraphClient() as ag:
            models, _ = ag.query_entity(MODEL, [query_data])
        if len(models) == 0:
            return {}
        return models[0]

    @staticmethod
    def get_organization_option(items: list, result: list):
        for item in items:
            result.append(
                dict(
                    id=item["id"],
                    name=item["name"],
                    is_default=False,
                    type="str",
                )
            )
            if item["subGroups"]:
                ModelManage.get_organization_option(item["subGroups"], result)

    @staticmethod
    def search_model_attr(model_id: str, language: str = "en"):
        """
        查询模型属性
        """
        model_info = ModelManage.search_model_info(model_id)
        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
        # TODO 语言包
        # lan = SettingLanguage(language)
        # model_attr = lan.get_val("ATTR", model_id)
        # for attr in attrs:
        #     if model_attr:
        #         attr["attr_name"] = model_attr.get(attr["attr_id"]) or attr["attr_name"]
        return attrs

    @staticmethod
    def search_model_attr_v2(model_id: str):
        """
        查询模型属性
        """
        model_info = ModelManage.search_model_info(model_id)
        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
        attr_types = {attr["attr_type"] for attr in attrs}
        system_mgmt_client = SystemMgmt()

        if ORGANIZATION in attr_types:
            groups = UserGroup.get_all_groups(system_mgmt_client)
            # 获取默认的第一个根组织
            groups = groups if groups else []
            option = []
            ModelManage.get_organization_option(groups, option)
            for attr in attrs:
                if attr["attr_type"] == ORGANIZATION:
                    attr.update(option=option)

        if USER in attr_types:
            users = UserGroup.user_list(system_mgmt_client, {"search": ""})
            option = [
                dict(
                    # id=user["username"],
                    id=user["id"],
                    name=user["username"],
                    is_default=False,
                    type="str",
                )
                for user in users["users"]
            ]
            for attr in attrs:
                if attr["attr_type"] == USER:
                    attr.update(option=option)

        return attrs

    @staticmethod
    def model_association_create(**data):
        """
        创建模型关联
        """
        with GraphClient() as ag:
            try:
                edge = ag.create_edge(
                    MODEL_ASSOCIATION,
                    data["src_id"],
                    MODEL,
                    data["dst_id"],
                    MODEL,
                    data,
                    "model_asst_id",
                )
            except BaseAppException as e:
                if e.message == "edge already exists":
                    raise BaseAppException("model association repetition")
                else:
                    raise BaseAppException(e.message)
        return edge

    @staticmethod
    def model_association_delete(id: int):
        """
        删除模型关联
        """
        with GraphClient() as ag:
            ag.delete_edge(id)

    @staticmethod
    def model_association_info_search(model_asst_id: str):
        """
        查询模型关联详情
        """
        with GraphClient() as ag:
            query_data = {
                "field": "model_asst_id",
                "type": "str=",
                "value": model_asst_id,
            }
            edges = ag.query_edge(MODEL_ASSOCIATION, [query_data])
        if len(edges) == 0:
            return {}
        return edges[0]

    @staticmethod
    def model_association_search(model_id: str):
        """
        查询模型所有的关联
        """
        query_list = [
            {"field": "src_model_id", "type": "str=", "value": model_id},
            {"field": "dst_model_id", "type": "str=", "value": model_id},
        ]
        with GraphClient() as ag:
            edges = ag.query_edge(MODEL_ASSOCIATION, query_list, param_type="OR")

        return edges

    @staticmethod
    def check_model_exist_association(model_id):
        """模型存在关联关系"""
        edges = ModelManage.model_association_search(model_id)
        if edges:
            raise BaseAppException("model association exist")

    @staticmethod
    def check_model_exist_inst(model_id):
        """模型存在实例"""
        params = [{"field": "model_id", "type": "str=", "value": model_id}]
        with GraphClient() as ag:
            _, count = ag.query_entity(INSTANCE, params, page=dict(skip=0, limit=1))
        if count > 0:
            raise BaseAppException("model exist instance")

    # ===========

    @staticmethod
    def get_max_order_id(classification_id: str):
        """
        获取当前最大的 order_id
        Args:
            classification_id: 分类ID
        """
        with GraphClient() as ag:
            models, _ = ag.query_entity(MODEL,
                                        [{"field": "classification_id", "type": "str=", "value": classification_id}],
                                        order="order_id", order_type="desc", page={"skip": 0, "limit": 1})
            if not models:
                return 0
            return models[0].get("order_id", 0)

    @staticmethod
    def update_model_orders(model_orders: list):
        """
        批量更新模型排序
        Args:
            model_orders: [{"model_id": "model_1", "order_id": 1}, ...]
        """
        with GraphClient() as ag:
            for order_info in model_orders:
                model_query = {"field": "model_id", "type": "str=", "value": order_info["model_id"]}
                models, model_count = ag.query_entity(MODEL, [model_query])
                if model_count == 0:
                    continue
                model_info = models[0]
                ag.set_entity_properties(
                    MODEL,
                    [model_info["_id"]],
                    {"order_id": order_info["order_id"]},
                    {},
                    [],
                    False
                )
        return True

    @staticmethod
    def reset_all_model_orders():
        """
        重置所有模型的 order_id
        按照分类分组，每个分类内部从1开始排序
        Returns:
            bool: 更新是否成功
        """
        with GraphClient() as ag:
            # 获取所有模型并按classification_id分组
            models, _ = ag.query_entity(MODEL, [], order="classification_id")

            # 按classification_id分组
            grouped_models = {}
            for model in models:
                classification_id = model["classification_id"]
                if classification_id not in grouped_models:
                    grouped_models[classification_id] = []
                grouped_models[classification_id].append(model)

            # 为每个分组内的模型更新order_id
            for classification_id, group_models in grouped_models.items():
                for index, model in enumerate(group_models, start=1):
                    ag.set_entity_properties(
                        MODEL,
                        [model["_id"]],
                        {"order_id": index},
                        {},
                        [],
                        False
                    )

        return True
