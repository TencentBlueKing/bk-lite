"""即时告警内存匹配，与批量关联规则使用同一严格字段契约。"""

from apps.alerts.utils.rule_catalog import model_fields
from apps.alerts.utils.typed_rules import matches_payload


class InstantMatcher:
    FIELD_MAP = model_fields("correlation")

    @staticmethod
    def match_in_memory(event, match_rules):
        # 即时旁路禁止无条件匹配。
        payload = {}
        for key, field in InstantMatcher.FIELD_MAP.items():
            value = event
            for part in field.split("__"):
                value = getattr(value, part, None)
            payload[key] = value
        return bool(match_rules) and matches_payload(payload, match_rules, "correlation")

    @staticmethod
    def _eval_condition(event, condition):
        return InstantMatcher.match_in_memory(event, [[condition]])
