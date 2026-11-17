"""通用查询条件组。整组一个逻辑关系，缺省 AND。"""


class ConditionGroupError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def parse_condition_group(raw) -> tuple[str, list[dict]]:
    """解析条件组。旧的行列表按 AND。空组表示不过滤。"""
    if raw in (None, "", []):
        return "AND", []
    logic = "AND"
    items = raw
    if isinstance(raw, dict):
        if raw and "items" not in raw and "logic" not in raw:
            raise ConditionGroupError("条件过滤格式错误")
        logic = str(raw.get("logic") or "AND").strip().upper()
        items = raw.get("items", [])
    if logic not in {"AND", "OR"}:
        raise ConditionGroupError("条件关系只支持 AND 或 OR")
    if items in (None, []):
        return logic, []
    if not isinstance(items, list):
        raise ConditionGroupError("条件过滤格式错误")
    parsed = []
    for item in items:
        if not isinstance(item, dict):
            raise ConditionGroupError("条件过滤格式错误")
        field = item.get("field")
        op = item.get("op") if item.get("op") not in (None, "") else item.get("type")
        if field in (None, "") or op in (None, ""):
            raise ConditionGroupError("条件过滤必须给出字段和运算符")
        parsed.append({"field": str(field), "op": str(op), "value": item.get("value")})
    return logic, parsed
