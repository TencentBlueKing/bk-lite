from typing import Dict, List


def _cmp(actual, operator: str, expected) -> bool:
    a = "" if actual is None else str(actual)
    e = "" if expected is None else str(expected)
    if operator in ("eq", "等于"):
        return a == e
    if operator in ("ne", "不等于"):
        return a != e
    if operator in ("contains", "包含"):
        return e.lower() in a.lower()
    if operator in ("not_contains", "不包含"):
        return e.lower() not in a.lower()
    if operator in ("in", "字中串"):
        return a in expected if isinstance(expected, (list, tuple, set)) else a in e
    if operator == "not_in":
        return a not in expected if isinstance(expected, (list, tuple, set)) else a not in e
    return False


def _match_group(event: Dict, group: List[Dict]) -> bool:
    for cond in group:
        if cond.get("key") not in event or event.get(cond.get("key")) in (None, ""):
            return False
        if not _cmp(event.get(cond["key"]), cond.get("operator", "eq"), cond.get("value")):
            return False
    return True


def event_matches(event: Dict, match_rules: List[List[Dict]]) -> bool:
    """OR-of-AND：空规则匹配全部；任一 AND 组全真即真。"""
    if not match_rules:
        return True
    return any(_match_group(event, group) for group in match_rules if group)
