import json
import re
from typing import Any, Iterable

import yaml

from apps.log.services.log_extractor.semantics import NormalizedRule, normalize_rule, parse_path


class _LiteralDumper(yaml.SafeDumper):
    pass


def _represent_string(dumper: yaml.SafeDumper, value: str):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_LiteralDumper.add_representer(str, _represent_string)


def _vrl_string(value: Any) -> str:
    if isinstance(value, str):
        value = value.replace("$", "$$")
    return json.dumps(value, ensure_ascii=False)


def _vrl_regex(value: str) -> str:
    return "r'" + value.replace("$", "$$").replace("'", "\\'") + "'"


def _vrl_replacement(value: str) -> str:
    # Vector 在解析配置时先执行环境变量插值；双写 $ 后，VRL 才能收到规则保存的逻辑替换串。
    return _vrl_string(value)


def _vrl_path(value: str | tuple[str, ...]) -> str:
    path = parse_path(value) if isinstance(value, str) else value
    result = "."
    for segment in path:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", segment):
            result += ("" if result == "." else ".") + segment
        else:
            result += ("" if result == "." else ".") + _vrl_string(segment)
    return result


def _compile_condition(condition: dict[str, Any]) -> str:
    clauses = []
    for item in condition["conditions"]:
        path = _vrl_path(item["field"])
        op = item["op"]
        if op == "exists":
            clauses.append(f"exists({path})")
        elif op == "!exists":
            clauses.append(f"!exists({path})")
        elif op in {"==", "!="}:
            value = item["value"]
            if value is None:
                type_guard = f"is_null({path})"
            elif isinstance(value, bool):
                type_guard = f"is_boolean({path})"
            elif isinstance(value, int):
                type_guard = f"is_integer({path})"
            elif isinstance(value, float):
                type_guard = f"is_float({path})"
            else:
                type_guard = f"is_string({path})"
            clauses.append(f"exists({path}) && {type_guard} && {path} {op} {_vrl_string(value)}")
        elif op in {"contains", "!contains"}:
            contains = f"contains(string!({path}), {_vrl_string(item['value'])})"
            clauses.append(f"is_string({path}) && !{contains}" if op == "!contains" else f"is_string({path}) && {contains}")
        elif op == "startswith":
            clauses.append(f"is_string({path}) && starts_with(string!({path}), {_vrl_string(item['value'])})")
        else:
            clauses.append(f"is_string({path}) && ends_with(string!({path}), {_vrl_string(item['value'])})")
    if not clauses:
        return "true"
    separator = " && " if condition["mode"] == "AND" else " || "
    return "(" + separator.join(clauses) + ")"


def _compile_assignments(rule: NormalizedRule) -> list[str]:
    source = _vrl_path(rule.source_path)
    target = _vrl_path(rule.target_path) if rule.target_path else None
    config = rule.config
    lines: list[str] = ["_extract_ok = false"]
    if rule.extractor_type == "copy":
        lines.append(f"{target} = {source}")
        lines.append("_extract_ok = true")
    elif rule.extractor_type == "split":
        lines.extend(
            [
                f"if is_string({source}) {{",
                f"  _parts = split(string!({source}), {_vrl_string(config['delimiter'])})",
                f"  _value, _get_err = get(_parts, [{config['index']}])",
                "  if _get_err == null && _value != null {",
                f"    {target} = _value",
                "    _extract_ok = true",
                "  }",
                "}",
            ]
        )
    elif rule.extractor_type == "kv":
        lines.extend(
            [
                f"if is_string({source}) {{",
                f"  _parsed, _err = parse_key_value(string!({source}), key_value_delimiter: {_vrl_string(config['key_value_delimiter'])}, field_delimiter: {_vrl_string(config['field_delimiter'])})",
                "  if _err == null {",
            ]
        )
        mapping = config["field_mapping"]
        if mapping:
            for key, output in sorted(mapping.items()):
                lines.extend(
                    [
                        f"    _value, _get_err = get(_parsed, [{_vrl_string(key)}])",
                        "    if _get_err == null && _value != null {",
                        f"      {_vrl_path(output)} = _value",
                        "      _extract_ok = true",
                        "    }",
                    ]
                )
        else:
            lines.extend(
                [
                    "    del(_parsed.instance_id)",
                    "    del(_parsed.source_type)",
                    "    del(_parsed.timestamp)",
                    "    if length(_parsed) > 0 {",
                    "      . = merge(., _parsed)",
                    "      _extract_ok = true",
                    "    }",
                ]
            )
        lines.extend(["  }", "}"])
    elif rule.extractor_type == "regex":
        lines.extend(
            [
                f"if is_string({source}) {{",
                f"  _parsed, _err = parse_regex(string!({source}), {_vrl_regex(config['pattern'])})",
                "  if _err == null {",
            ]
        )
        mapping = config["group_mapping"]
        if mapping:
            for key, output in sorted(mapping.items()):
                lines.extend(
                    [
                        f"    _value, _get_err = get(_parsed, [{_vrl_string(key)}])",
                        "    if _get_err == null && _value != null {",
                        f"      {_vrl_path(output)} = _value",
                        "      _extract_ok = true",
                        "    }",
                    ]
                )
        else:
            lines.extend(
                [
                    "    del(_parsed.instance_id)",
                    "    del(_parsed.source_type)",
                    "    del(_parsed.timestamp)",
                    "    if length(_parsed) > 0 {",
                    "      . = merge(., _parsed)",
                    "      _extract_ok = true",
                    "    }",
                ]
            )
        lines.extend(["  }", "}"])
    elif rule.extractor_type == "regex_replace":
        output = target or source
        lines.extend(
            [
                f"if is_string({source}) && match(string!({source}), {_vrl_regex(config['pattern'])}) {{",
                f"  {output} = replace(string!({source}), {_vrl_regex(config['pattern'])}, {_vrl_replacement(config['replacement'])}, count: -1)",
                "  _extract_ok = true",
                "}",
            ]
        )
    else:
        lines.extend(
            [
                f"if is_string({source}) {{",
                f"  _parsed, _err = parse_json(string!({source}))",
                "  if _err == null && is_object(_parsed) {",
            ]
        )
        if target:
            lines.append(f"    {target} = _parsed")
            lines.append("    _extract_ok = true")
        else:
            lines.extend(
                [
                    "    del(_parsed.instance_id)",
                    "    del(_parsed.source_type)",
                    "    del(_parsed.timestamp)",
                    "    if length(_parsed) > 0 {",
                    "      . = merge(., _parsed)",
                    "      _extract_ok = true",
                    "    }",
                ]
            )
        lines.extend(["  }", "}"])
    if rule.delete_source:
        lines.extend(["if _extract_ok {", f"  del({source})", "}"])
    return lines


def _compile_rule(record: Any) -> list[str]:
    normalized = normalize_rule(
        {
            "extractor_type": record.extractor_type,
            "source_field": record.source_field,
            "target_field": record.target_field,
            "condition": record.condition,
            "config": record.config,
            "delete_source": record.delete_source,
        }
    )
    instance = _vrl_string(str(record.collect_instance_id))
    predicate = f".instance_id == {instance} && {_compile_condition(normalized.condition)} && exists({_vrl_path(normalized.source_path)})"
    lines = [f"if {predicate} {{"]
    lines.extend(f"  {line}" for line in _compile_assignments(normalized))
    lines.append("}")
    return lines


def compile_system_vector_config(records: Iterable[Any]) -> str:
    ordered = sorted(records, key=lambda item: (str(item.collect_instance_id), item.sort_order, item.id))
    source_lines: list[str] = []
    for record in ordered:
        source_lines.extend(_compile_rule(record))
    extractor_source = "\n".join(source_lines) if source_lines else ". = ."
    config = {
        "sources": {
            "server_nats": {
                "type": "nats",
                "url": "${VECTOR_NATS_SERVERS}",
                "subject": "vector",
                "connection_name": "system-vector",
                "auth": {
                    "strategy": "user_password",
                    "user_password": {
                        "user": "${NATS_ADMIN_USERNAME}",
                        "password": "${NATS_ADMIN_PASSWORD}",
                    },
                },
                "decoding": {"codec": "json"},
            }
        },
        "transforms": {
            "normalize_event": {"type": "remap", "inputs": ["server_nats"], "source": ". = ."},
            "log_extractors": {"type": "remap", "inputs": ["normalize_event"], "drop_on_error": False, "source": extractor_source},
        },
        "sinks": {
            "victoria_logs": {
                "type": "http",
                "inputs": ["log_extractors"],
                "uri": "${VECTOR_VICTORIA_LOGS_URL}/insert/jsonline?_stream_fields=streams&_msg_field=message&_time_field=timestamp",
                "method": "post",
                "encoding": {"codec": "json"},
                "framing": {"method": "newline_delimited"},
                "healthcheck": {"enabled": False},
            }
        },
    }
    content = yaml.dump(config, Dumper=_LiteralDumper, allow_unicode=True, sort_keys=False, default_flow_style=False, width=120)
    _validate_compiled_config(content)
    return content


def _validate_compiled_config(content: str) -> None:
    parsed = yaml.safe_load(content)
    if not isinstance(parsed, dict) or set(parsed) != {"sources", "transforms", "sinks"}:
        raise ValueError("中心 Vector 配置拓扑无效")
    if parsed["transforms"].get("log_extractors", {}).get("inputs") != ["normalize_event"]:
        raise ValueError("日志提取 transform 输入无效")
    if parsed["sinks"].get("victoria_logs", {}).get("inputs") != ["log_extractors"]:
        raise ValueError("VictoriaLogs sink 输入无效")
    source = parsed["transforms"]["log_extractors"].get("source")
    if not isinstance(source, str) or not source:
        raise ValueError("日志提取 VRL 不能为空")
