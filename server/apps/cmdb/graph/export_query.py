"""导出专用的有界端点查询，兼容缺少边端点属性的存量关系。"""

from apps.cmdb.services.instance_identity import normalize_inst_uuid

EXPORT_BATCH_SIZE = 500
EXPORT_ASSOCIATION_FIELDS = (
    "inst_uuid",
    "model_asst_id",
    "peer_uuid",
    "peer_name",
    "edge_id",
    "src_model_id",
    "dst_model_id",
)


def entity_projection(fields):
    """查询投影使用已校验字段名，保留同进程工作集的内部节点 ID。"""
    from apps.cmdb.graph.validators import CQLValidator

    field_names = [CQLValidator.validate_field(field) for field in dict.fromkeys(fields) if field != "_id"]
    return "{_id: ID(n)" + "".join(f", {field}: n.{field}" for field in field_names) + "} AS export_record"


def export_association_queries(model_id, inst_uuids, association_ids):
    if not inst_uuids or not association_ids:
        return []
    if len(inst_uuids) > EXPORT_BATCH_SIZE:
        raise ValueError("导出关联查询超过批次上限")
    params = {
        "model_id": model_id,
        "inst_uuids": list(dict.fromkeys(normalize_inst_uuid(value) for value in inst_uuids)),
        "association_ids": list(dict.fromkeys(association_ids)),
    }
    queries = []
    for pattern, src, dst in (
        ("(n)-[r:instance_association]->(peer:instance)", "n", "peer"),
        ("(n)<-[r:instance_association]-(peer:instance)", "peer", "n"),
    ):
        # 先定位授权工作集中的节点，再沿邻接关系展开；不依赖边冗余属性。
        statement = (
            "MATCH (n:instance) WHERE n.inst_uuid IN $inst_uuids AND n.model_id = $model_id "
            "WITH n MATCH " + pattern + " WHERE r.model_asst_id IN $association_ids "
            "RETURN n.inst_uuid AS inst_uuid, r.model_asst_id AS model_asst_id, "
            "peer.inst_uuid AS peer_uuid, peer.inst_name AS peer_name, ID(r) AS edge_id, "
            f"{src}.model_id AS src_model_id, {dst}.model_id AS dst_model_id "
            "ORDER BY edge_id"
        )
        queries.append((statement, params))
    return queries
