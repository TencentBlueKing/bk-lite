# -- coding: utf-8 --
"""幂等初始化 IPAM 模型增量：子网新字段、ip 描述、ip--connect-->host/network 关联、对账登记表种子。"""
from django.core.management import BaseCommand
from apps.cmdb.services.model import ModelManage
from apps.core.logger import cmdb_logger as logger

SUBNET_NEW_ATTRS = [
    {
        "attr_id": "gateway",
        "attr_name": "网关",
        "attr_type": "str",
        "attr_group": "基本信息",
        "is_required": False,
        "editable": True,
        "is_only": False,
    },
    {
        "attr_id": "vlan_id",
        "attr_name": "VLAN",
        "attr_type": "int",
        "attr_group": "基本信息",
        "is_required": False,
        "editable": True,
        "is_only": False,
    },
    {
        "attr_id": "usage_type",
        "attr_name": "用途类型",
        "attr_type": "enum",
        "attr_group": "基本信息",
        "is_required": False,
        "editable": True,
        "is_only": False,
        "enum_select_mode": "single",
        "option": [
            {"id": "business", "name": "业务"},
            {"id": "management", "name": "管理"},
            {"id": "dmz", "name": "DMZ"},
            {"id": "interconnect", "name": "互联"},
            {"id": "other", "name": "其他"},
        ],
    },
    {
        "attr_id": "owner",
        "attr_name": "负责人",
        "attr_type": "user",
        "attr_group": "基本信息",
        "is_required": False,
        "editable": True,
        "is_only": False,
    },
]

IP_NEW_ATTRS = [
    {
        "attr_id": "description",
        "attr_name": "描述",
        "attr_type": "str",
        "attr_group": "基本信息",
        "is_required": False,
        "editable": True,
        "is_only": False,
    },
    {
        "attr_id": "ip_status",
        "attr_name": "IP状态",
        "attr_type": "enum",
        "attr_group": "基本信息",
        "is_required": False,
        "editable": True,
        "is_only": False,
        "enum_select_mode": "single",
        "default_value": ["unknown"],
        "option": [
            {"id": "online", "name": "在线"},
            {"id": "offline", "name": "离线"},
            {"id": "conflict", "name": "冲突"},
            {"id": "unknown", "name": "未知"},
        ],
    },
    {
        "attr_id": "ip_allocated_status",
        "attr_name": "分配状态",
        "attr_type": "enum",
        "attr_group": "基本信息",
        "is_required": False,
        "editable": True,
        "is_only": False,
        "enum_select_mode": "single",
        "default_value": ["available"],
        "option": [
            {"id": "available", "name": "可分配"},
            {"id": "allocated", "name": "已分配"},
            {"id": "reserved", "name": "已预留"},
        ],
    },
    {
        "attr_id": "ip_type",
        "attr_name": "IP类型",
        "attr_type": "enum",
        "attr_group": "基本信息",
        "is_required": False,
        "editable": True,
        "is_only": False,
        "enum_select_mode": "single",
        "option": [
            {"id": "static", "name": "静态"},
            {"id": "dynamic", "name": "动态"},
            {"id": "float", "name": "浮动VIP"},
            {"id": "gateway", "name": "网关"},
            {"id": "reserved", "name": "保留"},
        ],
    },
    {
        "attr_id": "ip_user",
        "attr_name": "使用人",
        "attr_type": "user",
        "attr_group": "基本信息",
        "is_required": False,
        "editable": True,
        "is_only": False,
    },
]

RECONCILE_SOURCES = [("host", "ip_addr"), ("network", "ip")]


def _ensure_attrs(model_id: str, new_attrs: list):
    existing_ids = {a["attr_id"] for a in (ModelManage.search_model_attr(model_id) or [])}
    for attr in new_attrs:
        if attr["attr_id"] in existing_ids:
            continue
        ModelManage.create_model_attr(model_id, dict(attr), username="system")
        logger.info(f"[ipam_init] 新增属性 {model_id}.{attr['attr_id']}")


def _ensure_association(src_model: str, dst_model: str, asst_id: str):
    from apps.core.exceptions.base_app_exception import BaseAppException

    model_asst_id = f"{src_model}_{asst_id}_{dst_model}"
    src = ModelManage.search_model_info(src_model)
    dst = ModelManage.search_model_info(dst_model)
    try:
        ModelManage.model_association_create(
            src_id=src["_id"],
            dst_id=dst["_id"],
            model_asst_id=model_asst_id,
            src_model_id=src_model,
            dst_model_id=dst_model,
            asst_id=asst_id,
            mapping="n:n",
        )
        logger.info(f"[ipam_init] 新增关联 {model_asst_id}")
    except BaseAppException:
        pass  # 已存在则幂等跳过


def _seed_sources():
    from apps.cmdb.models.ipam_models import IPAMReconcileSource

    for model_id, ip_attr_id in RECONCILE_SOURCES:
        IPAMReconcileSource.objects.get_or_create(
            model_id=model_id, ip_attr_id=ip_attr_id, defaults={"enabled": True}
        )


def run_ipam_init():
    _ensure_attrs("subnet", SUBNET_NEW_ATTRS)
    _ensure_attrs("ip", IP_NEW_ATTRS)
    _ensure_association("ip", "host", "connect")
    _ensure_association("ip", "network", "connect")
    _seed_sources()


class Command(BaseCommand):
    help = "初始化 IPAM 增量（子网字段/ip 描述/关联/对账登记表）"

    def handle(self, *args, **options):
        logger.info("[ipam_init] 开始...")
        run_ipam_init()
        logger.info("[ipam_init] 完成")
