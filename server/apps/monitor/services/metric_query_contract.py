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
