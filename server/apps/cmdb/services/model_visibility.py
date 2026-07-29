"""CMDB 面向业务读取的模型有效可见性策略。"""

from collections.abc import Iterable

from apps.cmdb.constants.constants import CLASSIFICATION, MODEL
from apps.cmdb.graph.drivers.graph_client import GraphClient


class BusinessModelVisibility:
    """统一判定模型及其所属分类是否对业务入口有效可见。"""

    @classmethod
    def is_visible(cls, model: dict | None) -> bool:
        if not model or not model.get("is_visible", True):
            return False
        if not model.get("classification_id"):
            return True
        return model.get("model_id") in cls.filter_models([model])

    @classmethod
    def resolve(
        cls,
        model_ids: Iterable[str] | None = None,
        *,
        language: str = "en",
    ) -> dict[str, dict]:
        del language  # 名称本地化由现有模型查询边界负责。
        requested_ids = list(dict.fromkeys(model_ids or []))
        model_params = []
        if model_ids is not None:
            if not requested_ids:
                return {}
            model_params.append(
                {"field": "model_id", "type": "str[]", "value": requested_ids}
            )

        with GraphClient() as graph:
            models, _ = graph.query_entity(MODEL, model_params)
        return cls.filter_models(models)

    @staticmethod
    def filter_models(
        models: Iterable[dict],
        *,
        graph: GraphClient | None = None,
    ) -> dict[str, dict]:
        """从已查询的模型集合中移除自身或父分类隐藏的模型。"""
        model_items = list(models)
        if not model_items:
            return {}
        classification_ids = list(
            dict.fromkeys(
                model.get("classification_id")
                for model in model_items
                if model.get("classification_id")
            )
        )
        if not classification_ids:
            return {
                model["model_id"]: model
                for model in model_items
                if model.get("is_visible", True)
            }
        if graph is None:
            with GraphClient() as graph_client:
                classifications, _ = graph_client.query_entity(
                    CLASSIFICATION,
                    [
                        {
                            "field": "classification_id",
                            "type": "str[]",
                            "value": classification_ids,
                        }
                    ]
                    if classification_ids
                    else [],
                )
        else:
            classifications, _ = graph.query_entity(
                CLASSIFICATION,
                [
                    {
                        "field": "classification_id",
                        "type": "str[]",
                        "value": classification_ids,
                    }
                ]
                if classification_ids
                else [],
            )

        classification_visibility = {
            item["classification_id"]: item.get("is_visible", True)
            for item in classifications
        }
        return {
            model["model_id"]: model
            for model in model_items
            if model.get("is_visible", True)
            and classification_visibility.get(
                model.get("classification_id"),
                True,
            )
        }

    @classmethod
    def filter_associations(
        cls,
        associations: Iterable[dict],
        *,
        language: str = "en",
    ) -> list[dict]:
        items = list(associations)
        endpoint_ids = [
            model_id
            for item in items
            for model_id in (
                item.get("src_model_id"),
                item.get("dst_model_id"),
            )
            if model_id
        ]
        visible_models = cls.resolve(endpoint_ids, language=language)
        result = []
        for item in items:
            src_model = visible_models.get(item.get("src_model_id"))
            dst_model = visible_models.get(item.get("dst_model_id"))
            if not src_model or not dst_model:
                continue
            association = dict(item)
            association["src_model_name"] = src_model.get("model_name", "")
            association["dst_model_name"] = dst_model.get("model_name", "")
            association["src_model_icn"] = src_model.get("icn", "")
            association["dst_model_icn"] = dst_model.get("icn", "")
            result.append(association)
        return result
