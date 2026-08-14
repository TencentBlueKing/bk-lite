# -- coding: utf-8 --
"""清掉 IP 模型上误加的主机表格字段。"""
from apps.core.logger import cmdb_logger as logger

IP_HOST_TABLE_ATTR_ID = "ip_table"


def drop_ip_host_table_attr(username: str = "admin") -> bool:
    """若 IP 模型仍有 ip_table，则删除属性及分组顺序。模型不存在或已删除时返回 False。"""
    from apps.cmdb.models.field_group import FieldGroup
    from apps.cmdb.services.model import ModelManage

    model_info = ModelManage.search_model_info("ip")
    if not model_info:
        return False
    attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
    if not any(attr.get("attr_id") == IP_HOST_TABLE_ATTR_ID for attr in attrs):
        return False
    ModelManage.delete_model_attr("ip", IP_HOST_TABLE_ATTR_ID, username=username)
    for group in FieldGroup.objects.filter(model_id="ip"):
        orders = list(group.attr_orders or [])
        if IP_HOST_TABLE_ATTR_ID not in orders:
            continue
        group.attr_orders = [item for item in orders if item != IP_HOST_TABLE_ATTR_ID]
        group.save(update_fields=["attr_orders"])
    logger.info("[IPAM] 已删除 IP 模型主机表格字段 ip_table")
    return True
