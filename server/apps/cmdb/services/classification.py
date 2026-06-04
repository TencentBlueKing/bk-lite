from apps.cmdb.constants.constants import (
    CLASSIFICATION,
    CREATE_CLASSIFICATION_CHECK_ATTR_MAP,
    MODEL,
    UPDATE_CLASSIFICATION_check_attr_map,
)
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.language.service import SettingLanguage
from apps.core.exceptions.base_app_exception import BaseAppException


class ClassificationManage(object):
    @staticmethod
    def create_model_classification(data: dict):
        """
        创建模型分类
        """
        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(CLASSIFICATION, [])
            result = ag.create_entity(CLASSIFICATION, data, CREATE_CLASSIFICATION_CHECK_ATTR_MAP, exist_items)
        return result

    @staticmethod
    def search_model_classification_info(classification_id: str):
        """
        查询模型分类属性
        """
        query_data = {
            "field": "classification_id",
            "type": "str=",
            "value": classification_id,
        }
        with GraphClient() as ag:
            models, _ = ag.query_entity(CLASSIFICATION, [query_data])
        if len(models) == 0:
            return {}
        return models[0]

    @staticmethod
    def check_classification_is_used(classification_id):
        """校验模型分类是否已经使用"""
        with GraphClient() as ag:
            model_query = {
                "field": "classification_id",
                "type": "str=",
                "value": classification_id,
            }
            _, model_count = ag.query_entity(MODEL, [model_query], page={"skip": 0, "limit": 1})
            if model_count > 0:
                raise BaseAppException("classification is used")

    @staticmethod
    def delete_model_classification(id: int):
        """
        删除模型分类
        """
        with GraphClient() as ag:
            ag.batch_delete_entity(CLASSIFICATION, [id])

    @staticmethod
    def update_model_classification(id: int, data: dict):
        """
        更新模型分类
        """
        # 不能更新classification_id、exist_model
        data.pop("classification_id", "")
        data.pop("exist_model", "")
        with GraphClient() as ag:
            exist_items, _ = ag.query_entity(CLASSIFICATION, [])
            # 排除当前正在更新的分类，避免自己和自己比较
            exist_items = [i for i in exist_items if i["_id"] != id]
            model = ag.set_entity_properties(
                CLASSIFICATION,
                [id],
                data,
                UPDATE_CLASSIFICATION_check_attr_map,
                exist_items,
            )
        return model[0]

    @staticmethod
    def search_model_classification(language: str = "en", include_hidden: bool = False):
        """
        查询模型分类
        Args:
            language: 语言
            include_hidden: True 时返回包含已隐藏（is_visible=False）的分类；
                默认 False 过滤掉
        """
        with GraphClient() as ag:
            classifications, _ = ag.query_entity(CLASSIFICATION, [])
            models, _ = ag.query_entity(MODEL, [])

        exist_model_classifications = {i["classification_id"] for i in models}
        for classification in classifications:
            classification["exist_model"] = (
                classification["classification_id"] in exist_model_classifications
            )
            if "order" not in classification:
                classification["order"] = 999
            if "is_visible" not in classification:
                classification["is_visible"] = True

        lan = SettingLanguage(language)
        for classification in classifications:
            classification["classification_name"] = (
                lan.get_val("CLASSIFICATION", classification["classification_id"])
                or classification["classification_name"]
            )

        if not include_hidden:
            classifications = [c for c in classifications if c.get("is_visible", True)]

        classifications.sort(key=lambda c: (c.get("order", 999), c["classification_id"]))
        return classifications
