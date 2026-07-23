import copy
import json
import re
from dataclasses import dataclass
from typing import Any

PROTECTED_FIELDS = {"instance_id", "source_type", "timestamp"}
EXTRACTOR_TYPES = {"copy", "split", "kv", "regex", "regex_replace", "json"}
CONDITION_OPERATORS = {"==", "!=", "contains", "!contains", "startswith", "endswith", "exists", "!exists"}
_SIMPLE_SEGMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_MISSING = object()


class RuleValidationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedRule:
    extractor_type: str
    source_path: tuple[str, ...]
    target_path: tuple[str, ...] | None
    condition: dict[str, Any]
    config: dict[str, Any]
    delete_source: bool


@dataclass(frozen=True)
class RuleExecutionResult:
    status: str
    error: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    event: dict[str, Any]
    results: list[RuleExecutionResult]


def parse_path(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        raise RuleValidationError("属性路径不能为空")
    segments: list[str] = []
    index = 0
    expect_segment = True
    while index < len(value):
        if value[index] == ".":
            if expect_segment:
                raise RuleValidationError("属性路径格式无效")
            expect_segment = True
            index += 1
            continue
        if not expect_segment and value[index] != "[":
            raise RuleValidationError("属性路径格式无效")
        if value.startswith('["', index):
            decoder = json.JSONDecoder()
            try:
                segment, consumed = decoder.raw_decode(value[index + 1 :])
            except json.JSONDecodeError as exc:
                raise RuleValidationError("属性路径引用段格式无效") from exc
            end = index + 1 + consumed
            if not isinstance(segment, str) or not segment or end >= len(value) or value[end] != "]":
                raise RuleValidationError("属性路径引用段格式无效")
            segments.append(segment)
            index = end + 1
        else:
            end = index
            while end < len(value) and value[end] not in ".[":
                end += 1
            segment = value[index:end]
            if not _SIMPLE_SEGMENT.fullmatch(segment):
                raise RuleValidationError("属性路径普通段格式无效")
            segments.append(segment)
            index = end
        expect_segment = False
    if expect_segment or not segments:
        raise RuleValidationError("属性路径格式无效")
    return tuple(segments)


def format_path(path: tuple[str, ...]) -> str:
    result = ""
    for segment in path:
        if _SIMPLE_SEGMENT.fullmatch(segment):
            result += ("." if result else "") + segment
        else:
            result += f"[{json.dumps(segment, ensure_ascii=False)}]"
    return result


def _normalize_mapping(value: Any, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuleValidationError(f"{field_name} 必须是对象")
    normalized: dict[str, str] = {}
    targets: set[tuple[str, ...]] = set()
    for source, target in value.items():
        if not isinstance(source, str) or not source:
            raise RuleValidationError(f"{field_name} 的键不能为空")
        target_path = parse_path(target)
        if target_path in targets:
            raise RuleValidationError(f"{field_name} 的目标路径不能重复")
        _ensure_writable(target_path)
        normalized[source] = format_path(target_path)
        targets.add(target_path)
    return normalized


def _normalize_condition(value: Any) -> dict[str, Any]:
    if value in (None, {}):
        return {"mode": "AND", "conditions": []}
    if not isinstance(value, dict) or set(value) - {"mode", "conditions"}:
        raise RuleValidationError("condition 结构无效")
    mode = value.get("mode", "AND")
    conditions = value.get("conditions", [])
    if mode not in {"AND", "OR"} or not isinstance(conditions, list):
        raise RuleValidationError("condition 结构无效")
    normalized = []
    for item in conditions:
        if not isinstance(item, dict) or set(item) - {"field", "op", "value"}:
            raise RuleValidationError("条件项结构无效")
        op = item.get("op")
        if op not in CONDITION_OPERATORS:
            raise RuleValidationError("条件操作符无效")
        path = parse_path(item.get("field"))
        if op in {"exists", "!exists"}:
            if "value" in item:
                raise RuleValidationError("存在性条件不能包含 value")
            normalized.append({"field": format_path(path), "op": op})
            continue
        condition_value = item.get("value", _MISSING)
        if condition_value is _MISSING or isinstance(condition_value, (dict, list)):
            raise RuleValidationError("条件 value 必须是 JSON 标量")
        if op in {"contains", "!contains", "startswith", "endswith"} and not isinstance(condition_value, str):
            raise RuleValidationError("字符串条件的 value 必须是字符串")
        normalized.append({"field": format_path(path), "op": op, "value": condition_value})
    return {"mode": mode, "conditions": normalized}


def _ensure_writable(path: tuple[str, ...]) -> None:
    if path[0] in PROTECTED_FIELDS:
        raise RuleValidationError("不能覆盖系统保护字段")


def _paths_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    shortest = min(len(left), len(right))
    return left[:shortest] == right[:shortest]


def _known_output_paths(
    extractor_type: str, source: tuple[str, ...], target: tuple[str, ...] | None, config: dict[str, Any]
) -> list[tuple[str, ...]] | None:
    if extractor_type in {"copy", "split"}:
        return [target] if target else []
    if extractor_type == "regex_replace":
        return [target or source]
    if extractor_type == "regex":
        mapping = config.get("group_mapping")
        if mapping:
            return [parse_path(path) for path in mapping.values()]
        return [(name,) for name in re.compile(config["pattern"]).groupindex]
    if extractor_type == "kv":
        mapping = config.get("field_mapping")
        return [parse_path(path) for path in mapping.values()] if mapping else None
    if extractor_type == "json":
        return [target] if target else None
    return []


def normalize_rule(data: dict[str, Any]) -> NormalizedRule:
    if not isinstance(data, dict):
        raise RuleValidationError("规则必须是对象")
    extractor_type = data.get("extractor_type")
    if extractor_type not in EXTRACTOR_TYPES:
        raise RuleValidationError("提取类型无效")
    source = parse_path(data.get("source_field", "message"))
    target_value = data.get("target_field")
    target = parse_path(target_value) if target_value else None
    if target:
        _ensure_writable(target)
    if extractor_type in {"copy", "split"} and target is None:
        raise RuleValidationError("该提取类型必须指定目标属性")
    if extractor_type in {"kv", "regex"} and target is not None:
        raise RuleValidationError("该提取类型不接受单一目标属性")
    config = data.get("config") or {}
    if not isinstance(config, dict):
        raise RuleValidationError("config 必须是对象")
    config = copy.deepcopy(config)
    allowed: dict[str, set[str]] = {
        "copy": set(),
        "split": {"delimiter", "index"},
        "kv": {"key_value_delimiter", "field_delimiter", "field_mapping"},
        "regex": {"pattern", "group_mapping"},
        "regex_replace": {"pattern", "replacement"},
        "json": set(),
    }
    if set(config) - allowed[extractor_type]:
        raise RuleValidationError("config 包含未声明字段")
    if extractor_type == "split":
        if not isinstance(config.get("delimiter"), str) or not config["delimiter"]:
            raise RuleValidationError("delimiter 必须是非空字符串")
        if not isinstance(config.get("index"), int) or isinstance(config["index"], bool) or config["index"] < 0:
            raise RuleValidationError("index 必须是非负整数")
    if extractor_type == "kv":
        for key in ("key_value_delimiter", "field_delimiter"):
            if not isinstance(config.get(key), str) or not config[key]:
                raise RuleValidationError(f"{key} 必须是非空字符串")
        config["field_mapping"] = _normalize_mapping(config.get("field_mapping"), "field_mapping")
    if extractor_type in {"regex", "regex_replace"}:
        pattern = config.get("pattern")
        if not isinstance(pattern, str) or not 1 <= len(pattern) <= 2000:
            raise RuleValidationError("pattern 长度必须为 1 到 2000")
        try:
            compiled_pattern = re.compile(pattern)
        except re.error as exc:
            raise RuleValidationError("pattern 不是有效正则") from exc
        _ensure_vector_regex_compatible(pattern)
        if extractor_type == "regex":
            if not compiled_pattern.groupindex:
                raise RuleValidationError("regex 至少需要一个命名捕获组")
            config["group_mapping"] = _normalize_mapping(config.get("group_mapping"), "group_mapping")
            if set(config["group_mapping"]) - set(compiled_pattern.groupindex):
                raise RuleValidationError("group_mapping 引用了不存在的捕获组")
        else:
            replacement = config.get("replacement")
            if not isinstance(replacement, str):
                raise RuleValidationError("replacement 必须是字符串")
            _validate_replacement(replacement, compiled_pattern)
    delete_source = data.get("delete_source", False)
    if not isinstance(delete_source, bool):
        raise RuleValidationError("delete_source 必须是布尔值")
    outputs = _known_output_paths(extractor_type, source, target, config)
    if outputs is not None:
        for output in outputs:
            _ensure_writable(output)
    if delete_source:
        if source[0] in PROTECTED_FIELDS or source == ("message",):
            raise RuleValidationError("不能删除系统保护字段或 message")
        if outputs is None:
            raise RuleValidationError("动态输出规则不能删除源属性")
        if any(_paths_overlap(source, output) for output in outputs):
            raise RuleValidationError("输出路径与源路径重叠")
    return NormalizedRule(
        extractor_type=extractor_type,
        source_path=source,
        target_path=target,
        condition=_normalize_condition(data.get("condition")),
        config=config,
        delete_source=delete_source,
    )


def _ensure_vector_regex_compatible(pattern: str) -> None:
    """Reject Python-only constructs unsupported by Vector 0.48's Rust regex engine."""
    if any(token in pattern for token in ("(?=", "(?!", "(?<=", "(?<!", "(?P=", "(?>", "(?(")):
        raise RuleValidationError("pattern 包含 Vector 0.48 不支持的正则结构")
    if re.search(r"(?<!\\)(?:\\\\)*\\[1-9]", pattern):
        raise RuleValidationError("pattern 包含 Vector 0.48 不支持的反向引用")


def _validate_replacement(value: str, pattern: re.Pattern[str]) -> None:
    index = 0
    while index < len(value):
        if value[index] != "$":
            index += 1
            continue
        if value.startswith("$$", index):
            index += 2
            continue
        match = re.match(r"\$\{([A-Za-z_][A-Za-z0-9_]*|[1-9][0-9]*)\}", value[index:])
        if not match:
            raise RuleValidationError("replacement 包含无效引用")
        reference = match.group(1)
        if reference.isdigit():
            if int(reference) > pattern.groups:
                raise RuleValidationError("replacement 引用了不存在的捕获组")
        elif reference not in pattern.groupindex:
            raise RuleValidationError("replacement 引用了不存在的捕获组")
        index += len(match.group(0))


def _get(event: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = event
    for segment in path:
        if not isinstance(current, dict) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


def _set(event: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = event
    for segment in path[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            child = {}
            current[segment] = child
        current = child
    current[path[-1]] = value


def _delete(event: dict[str, Any], path: tuple[str, ...]) -> None:
    current: Any = event
    parents: list[tuple[dict[str, Any], str]] = []
    for segment in path[:-1]:
        if not isinstance(current, dict) or segment not in current:
            return
        parents.append((current, segment))
        current = current[segment]
    if not isinstance(current, dict):
        return
    current.pop(path[-1], None)
    for parent, segment in reversed(parents):
        if parent.get(segment) == {}:
            parent.pop(segment)


def _condition_matches(event: dict[str, Any], condition: dict[str, Any]) -> bool:
    outcomes = []
    for item in condition["conditions"]:
        actual = _get(event, parse_path(item["field"]))
        op = item["op"]
        if op == "exists":
            outcome = actual is not _MISSING
        elif op == "!exists":
            outcome = actual is _MISSING
        elif actual is _MISSING:
            outcome = False
        elif op == "==":
            outcome = type(actual) is type(item["value"]) and actual == item["value"]
        elif op == "!=":
            outcome = type(actual) is type(item["value"]) and actual != item["value"]
        elif not isinstance(actual, str):
            outcome = False
        elif op == "contains":
            outcome = item["value"] in actual
        elif op == "!contains":
            outcome = item["value"] not in actual
        elif op == "startswith":
            outcome = actual.startswith(item["value"])
        else:
            outcome = actual.endswith(item["value"])
        outcomes.append(outcome)
    return all(outcomes) if condition["mode"] == "AND" else any(outcomes)


def _expand_replacement(value: str, match: re.Match[str]) -> str:
    result = ""
    index = 0
    while index < len(value):
        if value.startswith("$$", index):
            result += "$"
            index += 2
            continue
        reference = re.match(r"\$\{([^}]+)\}", value[index:]) if value[index] == "$" else None
        if reference:
            result += match.group(reference.group(1)) or ""
            index += len(reference.group(0))
            continue
        result += value[index]
        index += 1
    return result


def _execute_action(event: dict[str, Any], rule: NormalizedRule, source: Any) -> bool:
    kind = rule.extractor_type
    config = rule.config
    if kind == "copy":
        _set(event, rule.target_path, copy.deepcopy(source))
    elif not isinstance(source, str):
        return False
    elif kind == "split":
        parts = source.split(config["delimiter"])
        if config["index"] >= len(parts):
            raise ValueError("split_index")
        _set(event, rule.target_path, parts[config["index"]])
    elif kind == "kv":
        parsed: dict[str, str] = {}
        for part in source.split(config["field_delimiter"]):
            if config["key_value_delimiter"] not in part:
                continue
            key, value = part.split(config["key_value_delimiter"], 1)
            if key:
                parsed[key.strip()] = value.strip()
        mapping = config["field_mapping"]
        outputs = {key: parsed[key] for key in mapping if key in parsed} if mapping else parsed
        outputs = {key: value for key, value in outputs.items() if (parse_path(mapping[key]) if mapping else (key,))[0] not in PROTECTED_FIELDS}
        if not outputs:
            raise ValueError("kv_no_output")
        for key, value in outputs.items():
            _set(event, parse_path(mapping[key]) if mapping else (key,), value)
    elif kind == "regex":
        match = re.search(config["pattern"], source)
        if not match:
            raise ValueError("regex_no_match")
        mapping = config["group_mapping"]
        groups = match.groupdict()
        outputs = {key: groups[key] for key in mapping if groups.get(key) is not None} if mapping else groups
        outputs = {
            key: value
            for key, value in outputs.items()
            if value is not None and (parse_path(mapping[key]) if mapping else (key,))[0] not in PROTECTED_FIELDS
        }
        if not outputs:
            raise ValueError("regex_no_output")
        for key, value in outputs.items():
            _set(event, parse_path(mapping[key]) if mapping else (key,), value)
    elif kind == "regex_replace":
        pattern = re.compile(config["pattern"])
        if not pattern.search(source):
            raise ValueError("regex_no_match")
        output = pattern.sub(lambda match: _expand_replacement(config["replacement"], match), source)
        _set(event, rule.target_path or rule.source_path, output)
    elif kind == "json":
        parsed = json.loads(source)
        if not isinstance(parsed, dict):
            raise ValueError("json_not_object")
        if rule.target_path:
            _set(event, rule.target_path, parsed)
        else:
            outputs = {key: value for key, value in parsed.items() if key not in PROTECTED_FIELDS}
            if not outputs:
                raise ValueError("json_no_output")
            event.update(outputs)
    return True


def execute_rules(event: dict[str, Any], rules: list[NormalizedRule]) -> ExecutionResult:
    current = copy.deepcopy(event)
    results: list[RuleExecutionResult] = []
    for rule in rules:
        snapshot = copy.deepcopy(current)
        if not _condition_matches(snapshot, rule.condition):
            results.append(RuleExecutionResult("not_matched"))
            continue
        source = _get(snapshot, rule.source_path)
        if source is _MISSING:
            results.append(RuleExecutionResult("skipped", "source_missing"))
            continue
        try:
            wrote = _execute_action(current, rule, source)
        except (ValueError, TypeError, json.JSONDecodeError, re.error) as exc:
            results.append(RuleExecutionResult("failed", str(exc)))
            continue
        if not wrote:
            results.append(RuleExecutionResult("skipped", "source_type"))
            continue
        if rule.delete_source:
            _delete(current, rule.source_path)
        results.append(RuleExecutionResult("success"))
    return ExecutionResult(event=current, results=results)
