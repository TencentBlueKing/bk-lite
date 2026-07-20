# -*- coding: utf-8 -*-
"""
云资源成本分析 ORM 封装层。

职责:
- 把 CMDB 动态模型查询 (resource_bill / transaction_log + 图关联) 封装成纯函数
- 不做业务聚合,业务聚合留给 service 层
- 字段名以 2026-07-10 真实环境实测为准:
  - 对象类型 inst_type(参数) → resource_bill.object_type
  - 使用部门 user_department → resource_bill.user_department
  - 申请人   applying_user(参数) → resource_bill.applicant
  - 计费日期 billing_period → transaction_log.billing_date
- bill 维度走「先按 bill 维度筛 resource_bill → 图关联(instance_association_map)查 transaction_log」路径
- transaction_log 实例上无 _bill_id,归属关系由本层从关联结果反哺
"""
import logging
from datetime import date

from apps.cmdb.services.instance import InstanceManage

logger = logging.getLogger("cmdb")

RESOURCE_BILL_MODEL = "resource_bill"
TRANSACTION_LOG_MODEL = "transaction_log"

# 一次拉全量(报表聚合需要全集)
_MAX_PAGE_SIZE = 100000


def _perm(user_info: dict, model_id: str):
    """
    生成 InstanceManage.instance_list 需要的 permission_map。
    返回 None 表示无权限/身份缺失,调用方必须短路返回空,禁止越权返回全量。
    """
    from apps.cmdb.nats.nats import _build_nats_permission_map
    from apps.cmdb.constants.constants import PERMISSION_INSTANCES

    return _build_nats_permission_map(
        user_info or {}, model_id=model_id, permission_type=PERMISSION_INSTANCES
    )


def _bill_dim_params(*, inst_type=None, user_department=None, applying_user=None) -> list:
    """
    bill 维度筛选条件(2026-07-14 改为子串匹配,大小写不敏感)。

    str* 类型 + case_sensitive=False 在 FalkorDB 上由
    graph.format_str_like_params 翻译为:
      toLower(n.<field>) CONTAINS toLower($param)

    参数名保留业务语义,内部映射到真实字段:
      inst_type      → object_type
      user_department→ user_department
      applying_user  → applicant
    """
    params = []
    if inst_type:
        params.append({"field": "object_type", "type": "str*", "value": inst_type})
    if user_department:
        params.append({"field": "user_department", "type": "str*", "value": user_department})
    if applying_user:
        params.append({"field": "applicant", "type": "str*", "value": applying_user})
    return params


def _time_param(billing_period) -> list:
    """billing_date 区间条件(type=time,用 start/end)。"""
    if not billing_period:
        return []
    start, end = billing_period
    start = start.isoformat() if isinstance(start, date) else start
    end = end.isoformat() if isinstance(end, date) else end
    return [{"field": "billing_date", "type": "time", "start": start, "end": end}]


def _instance_list(model_id: str, params: list, permission_map: dict):
    """统一调用 InstanceManage.instance_list,返回 (list, count)。

    case_sensitive=False 让 str* 走 toLower(n.field) CONTAINS toLower($param),
    实现模糊筛选的大小写不敏感;str= 等其他 type 不读该参数,不受影响。
    """
    return InstanceManage.instance_list(
        model_id, params, 1, _MAX_PAGE_SIZE, "", permission_map, creator="",
        case_sensitive=False,
    )


def query_bills_by_filter(
    user_info: dict,
    *,
    inst_type=None,
    user_department=None,
    applying_user=None,
    billing_period=None,
):
    """
    按条件查询 resource_bill。

    只接受 bill 上的筛选维度(inst_type / user_department / applying_user)。
    log 上的维度(billing_period)传进来会被忽略并记录 WARN。

    Returns:
        (bills_list, total_count)
    """
    if billing_period is not None:
        logger.warning(
            "query_bills_by_filter 忽略 log 维度 billing_period=%s;"
            "该参数属于 transaction_log,不应传入 bill 查询",
            billing_period,
        )
    permission_map = _perm(user_info, RESOURCE_BILL_MODEL)
    if permission_map is None:
        return [], 0
    params = _bill_dim_params(
        inst_type=inst_type,
        user_department=user_department,
        applying_user=applying_user,
    )
    return _instance_list(RESOURCE_BILL_MODEL, params, permission_map)


def query_logs_by_filter(
    user_info: dict,
    *,
    inst_type=None,
    user_department=None,
    applying_user=None,
    billing_period=None,
):
    """
    按条件查询 transaction_log。

    **始终经 bill 解析归属**(不区分是否带 bill 维度):
    1. 按 bill 维度(inst_type / user_department / applying_user;全空=所有可见 bill)查 resource_bill
    2. bill 集合为空 → 返回 ([], 0)
    3. instance_association_map 关联出 log_id 集合,按 id[] (+billing_period) 查 log
    4. 给每条 log 反哺 _bill_id(log 实例本身无此字段),便于 service 层归属聚合

    统一走 bill 的好处:
    - 保证 log 永远带 _bill_id,distribution / instance_list 的分组聚合恒成立
    - 多租户正确:只返回「当前用户可见 bill」关联的 log

    Returns:
        (logs_list, total_count)
    """
    log_perm = _perm(user_info, TRANSACTION_LOG_MODEL)
    if log_perm is None:
        return [], 0

    bills, _ = query_bills_by_filter(
        user_info,
        inst_type=inst_type,
        user_department=user_department,
        applying_user=applying_user,
    )
    bill_ids = [int(b["_id"]) for b in bills]
    if not bill_ids:
        return [], 0

    relation = InstanceManage.instance_association_map(
        RESOURCE_BILL_MODEL, bill_ids, related_model=TRANSACTION_LOG_MODEL
    )
    log_to_bill = {int(lid): bid for bid, ids in relation.items() for lid in ids}
    log_ids = sorted(log_to_bill.keys())
    if not log_ids:
        return [], 0

    params = [{"field": "id", "type": "id[]", "value": log_ids}] + _time_param(billing_period)
    logs, count = _instance_list(TRANSACTION_LOG_MODEL, params, log_perm)
    for lg in logs:
        lg["_bill_id"] = log_to_bill.get(int(lg["_id"]))
    return logs, count


def query_bills_by_object_ids(user_info: dict, object_ids: list):
    """按图节点 id 批量查 resource_bill。"""
    if not object_ids:
        return [], 0
    permission_map = _perm(user_info, RESOURCE_BILL_MODEL)
    if permission_map is None:
        return [], 0
    params = [{"field": "id", "type": "id[]", "value": [int(i) for i in object_ids]}]
    return _instance_list(RESOURCE_BILL_MODEL, params, permission_map)
