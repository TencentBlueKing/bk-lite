"""一次性升级五入口存量规则；契约冻结于本迁移，不依赖运行期模型/目录。"""

import re
from copy import deepcopy

from django.db import migrations, transaction

# 迁移只保存转换所需的 2026-09-14 契约；后续业务目录变化不得修改这里。
EVENT_SCOPES = {"correlation", "shield", "enrichment"}
MODEL_NAMES = {
    "correlation": "AlarmStrategy",
    "assignment": "AlertAssignment",
    "shield": "AlertShield",
    "enrichment": "EnrichmentRule",
    "action": "ActionRule",
}
TEXT = {"eq", "ne", "contains", "not_contains"}
CANDIDATES = {"any_of", "none_of"}
SET = CANDIDATES | {"all_of"}
SEARCH = CANDIDATES | {"contains", "not_contains", "re"}
COMMON_FIELDS = {
    "title": TEXT,
    "level": CANDIDATES,
    "resource_type": CANDIDATES,
    "resource_id": CANDIDATES,
    "resource_name": SEARCH,
    "item": SEARCH,
}
EVENT_FIELDS = {**COMMON_FIELDS, "description": TEXT, "source_name": CANDIDATES, "push_source_id": CANDIDATES, "service": SEARCH, "location": SEARCH}
ALERT_FIELDS = {**COMMON_FIELDS, "content": TEXT, "source_names": SET, "push_source_ids": SET}


def field_spec(key, scope):
    fields = EVENT_FIELDS if scope in EVENT_SCOPES else ALERT_FIELDS
    if key not in fields:
        raise ValueError("字段不适用于当前规则，请重新配置")
    return {"operators": fields[key], "type": "list" if key in {"source_names", "push_source_ids"} else "str"}


def validate_condition(rule, scope):
    if not isinstance(rule, dict) or not isinstance(rule.get("key"), str):
        raise ValueError("匹配条件格式无效")
    spec = field_spec(rule["key"], scope)
    operator, value = rule.get("operator"), rule.get("value")
    if operator not in spec["operators"]:
        raise ValueError("操作符不适用于该字段类型，请重新配置")
    if operator in SET:
        if not isinstance(value, list) or not 1 <= len(value) <= 50:
            raise ValueError("列表匹配值须为 1 到 50 项的数组")
        values = value
    else:
        values = [value]
    if any(not isinstance(item, str) or not item.strip() or len(item) > 256 for item in values):
        raise ValueError("匹配值须为非空字符串，且不能超过 256 个字符")
    if operator == "re":
        try:
            re.compile(value)
        except re.error as error:
            raise ValueError("正则表达式无效") from error


def validate_rules(rules, scope):
    if not isinstance(rules, list) or len(rules) > 20:
        raise ValueError("条件组须为数组，最多 20 组")
    count = 0
    for group in rules:
        if not isinstance(group, list) or not group:
            raise ValueError("条件组不能为空")
        count += len(group)
        if count > 100:
            raise ValueError("匹配条件最多 100 条")
        for rule in group:
            validate_condition(rule, scope)


OPERATOR_ALIASES = {
    "等于": "eq",
    "不等于": "ne",
    "包含": "contains",
    "不包含": "not_contains",
    "正则": "re",
    "regex": "re",
    "字中串": "in",
}
# 来源是旧 StrategyMatcher.FIELD_MAP；“对象实例”在旧相关性中实际指资源名称。
CORRELATION_KEYS = {
    "标题": "title",
    "告警源": "source_name",
    "级别": "level",
    "类型对象": "resource_type",
    "对象实例": "resource_name",
    "内容": "description",
    "服务": "service",
    "位置": "location",
    "来源": "push_source_id",
    "资源ID": "resource_id",
    "指标": "item",
}


def _strings(value):
    values = value if isinstance(value, list) else [value]
    if not 1 <= len(values) <= 50:
        raise ValueError("候选值数量须在 1–50 之间")
    if any(isinstance(item, bool) or not isinstance(item, (str, int)) or not str(item).strip() for item in values):
        raise ValueError("旧值不是可转换的字符串或整数")
    return list(dict.fromkeys(str(item) for item in values))


class LegacyRuleConverter:
    def __init__(self, scope, apps, database):
        self.scope = scope
        self.apps = apps
        self.database = database
        self.event_scope = scope in EVENT_SCOPES

    def _source_names(self, value):
        values = _strings(value)
        sources = self.apps.get_model("alerts", "AlertSource")._base_manager.using(self.database)
        if self.scope == "enrichment":
            # 入库前丰富上下文的 source_id 是接入源业务编码，不是外键主键。
            selected = list(sources.filter(source_id__in=values).values_list("pk", "name"))
            expected_count = len(values)
        else:
            if any(not item.isdecimal() or not 0 < int(item) <= 9223372036854775807 for item in values):
                raise ValueError("旧告警源 ID 必须是正整数主键")
            ids = set(map(int, values))
            selected = list(sources.filter(pk__in=ids).values_list("pk", "name"))
            expected_count = len(ids)
        if len(selected) != expected_count:
            raise ValueError("旧告警源已不存在，无法解析名称")
        names = sorted({name for _, name in selected if name and name.strip()})
        if not names or len(names) != len({name for _, name in selected}):
            raise ValueError("旧告警源名称为空")
        selected_ids = {pk for pk, _ in selected}
        if sources.filter(name__in=names).exclude(pk__in=selected_ids).exists():
            raise ValueError("存在未选中的同名告警源，按名称迁移会扩大匹配范围")
        return names

    def _condition(self, condition):
        if not isinstance(condition, dict) or not isinstance(condition.get("key"), str):
            raise ValueError("匹配条件格式无效")
        rule = deepcopy(condition)
        key = rule["key"]
        if self.scope == "correlation":
            key = CORRELATION_KEYS.get(key, key)
        key = {"level_id": "level", "source": "source_name", "source__name": "source_name"}.get(key, key)
        if self.event_scope and key == "content":
            key = "description"
        if not self.event_scope:
            key = {"source_name": "source_names", "push_source_id": "push_source_ids"}.get(key, key)
        operator = rule.get("operator")
        if not isinstance(operator, str):
            raise ValueError("操作符格式无效")
        operator = OPERATOR_ALIASES.get(operator, operator)
        value = rule.get("value")
        if key == "source_id":
            if operator not in {"eq", "ne", "in", "not_in", "any_of", "none_of"}:
                raise ValueError("告警源 ID 的文本或正则条件不能转换为名称匹配")
            value = self._source_names(value)
            key = "source_name" if self.event_scope else "source_names"
        spec = field_spec(key, self.scope)
        rule.update(key=key, operator=operator, value=value)
        # 已符合当前目录的条件原样保留，不调整有效值的空白或顺序。
        try:
            validate_condition(rule, self.scope)
            return [[rule]]
        except ValueError:
            return self._convert_invalid(rule, spec)

    @staticmethod
    def _convert_invalid(rule, spec):
        operator, value = rule["operator"], rule["value"]
        if operator == "all_of" and spec["type"] == "list" and isinstance(value, list):
            return [[dict(rule, value=_strings(value))]]
        if operator in {"eq", "ne", "in", "not_in", "any_of", "none_of"}:
            negative = operator in {"ne", "not_in", "none_of"}
            if operator in {"in", "not_in", "any_of", "none_of"} and not isinstance(value, list):
                raise ValueError("旧候选操作符必须保存数组，不能猜测字符串分隔方式")
            values = _strings(value)
            if "any_of" in spec["operators"]:
                rule.update(operator="none_of" if negative else "any_of", value=values)
                return [[rule]]
            # 标题/正文的新编辑器只接受单文本，展开仍保持原 AND/OR。
            rules = [dict(rule, operator="ne" if negative else "eq", value=item) for item in values]
            return [rules] if negative else [[item] for item in rules]
        if operator in {"text_any", "text_all", "text_none"}:
            if not isinstance(value, list):
                raise ValueError("旧多关键词条件必须保存数组")
            values = _strings(value)
            rules = [dict(rule, operator="not_contains" if operator == "text_none" else "contains", value=item) for item in values]
            return [[item] for item in rules] if operator == "text_any" else [rules]
        if operator in {"contains", "not_contains", "re"}:
            if operator not in spec["operators"]:
                raise ValueError("新字段不支持旧文本/正则条件，不能改为集合包含")
            if isinstance(value, list):
                raise ValueError("旧文本条件保存了数组，无法确定原匹配语义")
            rule["value"] = _strings(value)[0]
            return [[rule]]
        raise ValueError("当前目录没有与旧操作符等价的条件")

    def convert(self, rules):
        if not isinstance(rules, list) or len(rules) > 20:
            raise ValueError("条件组必须是数组且最多 20 组")
        converted = []
        for group_index, group in enumerate(rules, 1):
            if not isinstance(group, list) or not group:
                raise ValueError(f"第 {group_index} 组为空或格式无效")
            branches = [[]]
            for condition_index, condition in enumerate(group, 1):
                try:
                    alternatives = self._condition(condition)
                    if len(converted) + len(branches) * len(alternatives) > 20:
                        raise ValueError("展开后超过 20 个条件组")
                    branches = [left + right for left in branches for right in alternatives]
                    validate_rules(converted + branches, self.scope)
                except (ValueError, TypeError) as error:
                    raise ValueError(f"第 {group_index} 组第 {condition_index} 条: {error}") from error
            converted.extend(branches)
        validate_rules(converted, self.scope)
        levels = {value for group in converted for rule in group if rule["key"] == "level" for value in rule["value"]}
        if levels:
            allowed = set(
                self.apps.get_model("alerts", "Level")
                ._base_manager.using(self.database)
                .filter(level_type="event" if self.event_scope else "alert")
                .values_list("level_id", flat=True)
            )
            if not levels <= {str(item) for item in allowed}:
                raise ValueError("级别目录中不存在旧规则选择的级别")
        return converted


def migrate_rules(apps, schema_editor):
    database = schema_editor.connection.alias
    # 显式覆盖整个数据步骤，包含不能自动转换的策略失败；不提交半套新旧配置。
    with transaction.atomic(using=database):
        for scope, model_name in MODEL_NAMES.items():
            queryset = apps.get_model("alerts", model_name)._base_manager.using(database)
            upper_id = queryset.order_by("-pk").values_list("pk", flat=True).first() or 0
            last_id = 0
            converter = LegacyRuleConverter(scope, apps, database)
            while last_id < upper_id:
                records = list(queryset.select_for_update().filter(pk__gt=last_id, pk__lte=upper_id).order_by("pk")[:200])
                if not records:
                    break
                for current in records:
                    if getattr(current, "match_type", None) == "all":
                        continue
                    try:
                        if scope == "action" and current.scope != "alert":
                            raise ValueError("处理规则不是告警作用域")
                        if getattr(current, "match_type", None) == "filter" and not current.match_rules:
                            raise ValueError("筛选模式的空规则不能转换为全部匹配")
                        converted = converter.convert(current.match_rules)
                    except (ValueError, TypeError) as error:
                        raise RuntimeError(
                            f"告警规则迁移失败 scope={scope} id={current.pk}: {error}。" "本次规则迁移已回滚；修正该策略后重新执行 migrate，禁止使用 --fake 跳过。"
                        ) from error
                    if converted != current.match_rules:
                        queryset.filter(pk=current.pk).update(match_rules=converted)
                last_id = records[-1].pk


class Migration(migrations.Migration):
    dependencies = [("alerts", "0032_alertassignment_priority")]

    # 多种旧格式映射到相同新格式，不能靠逆变换恢复；版本回退须恢复发布前数据库备份。
    operations = [migrations.RunPython(migrate_rules)]
