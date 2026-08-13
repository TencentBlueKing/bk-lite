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
