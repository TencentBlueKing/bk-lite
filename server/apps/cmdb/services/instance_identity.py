from uuid import UUID, uuid4

from apps.core.exceptions.base_app_exception import BaseAppException

INST_UUID_FIELD = "inst_uuid"
EDGE_SRC_UUID_FIELD = "src_inst_uuid"
EDGE_DST_UUID_FIELD = "dst_inst_uuid"
FORBIDDEN_EDGE_ENDPOINT_FIELDS = ("src_inst_id", "dst_inst_id")


def prepare_new_instance_identity(instance_data: dict) -> dict:
    """为新建实例注入不可变业务身份；常规调用方不得自带 inst_uuid。"""
    if INST_UUID_FIELD in instance_data:
        raise BaseAppException("inst_uuid 是系统保留字段")
    return {**instance_data, INST_UUID_FIELD: str(uuid4())}


def ensure_instance_identity_immutable(update_data: dict) -> None:
    """更新载荷中不得出现 inst_uuid（即使值未变）。"""
    if INST_UUID_FIELD in update_data:
        raise BaseAppException("inst_uuid 不可修改")


def normalize_inst_uuid(value: object) -> str:
    """校验并规范为小写、带连字符的 UUIDv4 字符串。"""
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BaseAppException("inst_uuid 必须是 UUIDv4") from exc
    if parsed.version != 4:
        raise BaseAppException("inst_uuid 必须是 UUIDv4")
    return str(parsed)


def optional_inst_uuid(value: object) -> str | None:
    """合法 UUIDv4 则返回规范字符串，否则 None。"""
    if value in (None, ""):
        return None
    try:
        return normalize_inst_uuid(value)
    except BaseAppException:
        return None


def optional_graph_id(value: object) -> str | None:
    """图内部数字 ID 的字符串形式；非纯数字返回 None。"""
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    return str(int(text))


def cmdb_link_identity(instance: dict | None) -> tuple[str | None, list[str]]:
    """跨 app 业务键 + 过渡期查找别名（UUID 优先，其次图 _id）。"""
    if not isinstance(instance, dict):
        return None, []
    inst_uuid = optional_inst_uuid(instance.get("inst_uuid"))
    aliases: list[str] = []
    if inst_uuid:
        aliases.append(inst_uuid)
    graph_id = optional_graph_id(instance.get("_id") if instance.get("_id") is not None else instance.get("inst_id"))
    if graph_id and graph_id not in aliases:
        aliases.append(graph_id)
    return inst_uuid, aliases


def collect_cmdb_id_candidates(*values: object) -> list[str]:
    """去重后的 cmdb_id 查找候选（UUID / 旧数字）。"""
    candidates: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            for item in collect_cmdb_id_candidates(*value):
                if item not in candidates:
                    candidates.append(item)
            continue
        if value in (None, ""):
            continue
        text = str(value).strip()
        if not text or text in candidates:
            continue
        candidates.append(text)
    return candidates


def expand_cmdb_id_lookup_candidates(cmdb_id: object, extra_aliases: object = None) -> list[str]:
    """把 UUID 与图 _id 互查，便于监控/节点命中尚未回填的行。"""
    candidates = collect_cmdb_id_candidates(cmdb_id, extra_aliases)
    inst_uuid = optional_inst_uuid(cmdb_id)
    graph_id = optional_graph_id(cmdb_id)
    try:
        from apps.cmdb.services.instance import InstanceManage

        entity = None
        if inst_uuid:
            entity = InstanceManage.query_entity_by_uuid(inst_uuid)
        elif graph_id:
            entity = InstanceManage.query_entity_by_id(int(graph_id))
        _, aliases = cmdb_link_identity(entity)
        for alias in aliases:
            if alias not in candidates:
                candidates.append(alias)
    except Exception:
        return candidates
    return candidates


def ensure_graph_instance_identity(label: str, properties: dict) -> dict:
    """图写入边界兜底：仅 instance 节点保证有规范 inst_uuid。

    供采集等旁路直写路径使用；已有合法 UUID 则规范化保留，缺失则生成。
    非 instance 标签原样返回。
    """
    result = dict(properties)
    if label != "instance":
        return result
    value = result.get(INST_UUID_FIELD)
    result[INST_UUID_FIELD] = normalize_inst_uuid(value) if value else str(uuid4())
    return result


def prepare_edge_endpoint_properties(
    properties: dict,
    *,
    src_inst_uuid: str | None = None,
    dst_inst_uuid: str | None = None,
) -> dict:
    """边写入边界：持久化 UUID 端点，剔除数字端点属性。"""
    result = {key: value for key, value in properties.items() if key not in FORBIDDEN_EDGE_ENDPOINT_FIELDS}
    src = result.get(EDGE_SRC_UUID_FIELD) or src_inst_uuid
    dst = result.get(EDGE_DST_UUID_FIELD) or dst_inst_uuid
    if not src or not dst:
        raise BaseAppException("边端点必须包含 src_inst_uuid/dst_inst_uuid")
    result[EDGE_SRC_UUID_FIELD] = normalize_inst_uuid(src)
    result[EDGE_DST_UUID_FIELD] = normalize_inst_uuid(dst)
    return result
