import re

from apps.monitor.utils.dimension import parse_instance_id


class AuthorizedMetricQueryError(ValueError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


def escape_metric_label_value(value) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def build_instance_matchers(instance_ids: tuple[str, ...], keys: list[str]) -> list[str]:
    values_by_key = {key: set() for key in keys}
    for instance_id in instance_ids:
        values = parse_instance_id(instance_id)
        if len(values) < len(keys):
            raise AuthorizedMetricQueryError(
                "监控实例标识与指标契约不匹配",
                code="instance_identity_invalid",
            )
        for index, key in enumerate(keys):
            value = values[index]
            if value in (None, ""):
                raise AuthorizedMetricQueryError(
                    "监控实例标识与指标契约不匹配",
                    code="instance_identity_invalid",
                )
            values_by_key[key].add(str(value))

    matchers = []
    for key, values in values_by_key.items():
        escaped_values = [escape_metric_label_value(re.escape(value)) for value in sorted(values)]
        matchers.append(f'{key}=~"{"|".join(escaped_values)}"')
    return matchers


def build_instance_matcher_groups(instance_ids: tuple[str, ...], keys: list[str]) -> list[list[str]]:
    """复合实例按完整身份生成 matcher，避免各维度正则集合交叉出未授权组合。"""
    if len(keys) <= 1:
        return [build_instance_matchers(instance_ids, keys)]

    groups = []
    for instance_id in instance_ids:
        values = parse_instance_id(instance_id)
        if len(values) < len(keys):
            raise AuthorizedMetricQueryError(
                "监控实例标识与指标契约不匹配",
                code="instance_identity_invalid",
            )
        group = []
        for index, key in enumerate(keys):
            value = values[index]
            if value in (None, ""):
                raise AuthorizedMetricQueryError(
                    "监控实例标识与指标契约不匹配",
                    code="instance_identity_invalid",
                )
            group.append(f'{key}="{escape_metric_label_value(value)}"')
        groups.append(group)
    return groups


def join_label_queries(template: str, matcher_groups: list[list[str]]) -> str:
    if not matcher_groups:
        return template.replace("__$labels__", "")
    queries = [template.replace("__$labels__", ", ".join(group)) for group in matcher_groups]
    if len(queries) == 1:
        return queries[0]
    return " or ".join(f"({query})" for query in queries)
