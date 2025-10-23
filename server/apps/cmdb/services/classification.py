from apps.cmdb.constants import (
    CLASSIFICATION,
    CREATE_CLASSIFICATION_CHECK_ATTR_MAP,
    MODEL,
    UPDATE_CLASSIFICATION_check_attr_map,
)
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.language.service import SettingLanguage


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
                raise Exception("classification is used")

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
    def search_model_classification(language: str = "en"):
        """
        查询模型分类
        """
        with GraphClient() as ag:
            classifications, _ = ag.query_entity(CLASSIFICATION, [])
            models, _ = ag.query_entity(MODEL, [])

        # 判断模型分类下是否存在模型
        exist_model_classifications = {i["classification_id"] for i in models}
        for classification in classifications:
            if classification["classification_id"] in exist_model_classifications:
                classification["exist_model"] = True
            else:
                classification["exist_model"] = False

        lan = SettingLanguage(language)

        for classification in classifications:
            classification["classification_name"] = (
                lan.get_val("CLASSIFICATION", classification["classification_id"])
                or classification["classification_name"]
            )

        return classifications
