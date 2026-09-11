import json

from apps.cmdb.constants.constants import MODEL, MODEL_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient


def parse_attrs(attrs: str):
    return json.loads(attrs.replace('\\"', '"'))


def search_model_info(model_id: str):
    query_data = [{"field": "model_id", "type": "str=", "value": model_id}]
    with GraphClient() as ag:
        models, _ = ag.query_entity(MODEL, query_data)
    if len(models) == 0:
        return {}
    return models[0]


def model_association_info_search(model_asst_id: str):
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


def model_association_search(
    model_id: str,
    *,
    business_only: bool = False,
    language: str = "en",
):
    query_list = [
        {"field": "src_model_id", "type": "str=", "value": model_id},
        {"field": "dst_model_id", "type": "str=", "value": model_id},
    ]
    with GraphClient() as ag:
        edges = ag.query_edge(MODEL_ASSOCIATION, query_list, param_type="OR")

    if business_only:
        from apps.cmdb.services.model_visibility import BusinessModelVisibility

        return BusinessModelVisibility.filter_associations(
            edges,
            language=language,
        )
    return edges
