from __future__ import annotations

import copy
import re
from collections import defaultdict, deque
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from apps.workflow_orchestration.services.definitions import DefinitionValidationError
from apps.workflow_orchestration.services.schedules import compile_schedule_config
from apps.workflow_orchestration.services.webhook_contracts import webhook_input_schema

TRIGGER_TYPES = {"FORM", "SCHEDULE", "WEBHOOK", "NATS"}
RETURN_TYPES = {"WEBHOOK"}
NODE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,99}$")
FILE_FORMATS = {"docx", "xlsx"}


def _validate_form_field_extension(key: str, schema: dict[str, Any]) -> None:
    widget = schema.get("x-widget")
    if widget == "target-selector":
        binding = schema.get("x-target-binding")
        if not isinstance(binding, dict) or binding.get("mode") != "runtime":
            raise DefinitionValidationError(f"资源选择字段 {key} 缺少运行时目标配置")
        sources = binding.get("allowedSources")
        operating_systems = binding.get("allowedOperatingSystems")
        if not isinstance(sources, list) or not sources or not set(sources).issubset({"node_mgmt", "job_mgmt"}):
            raise DefinitionValidationError(f"资源选择字段 {key} 的目标来源非法")
        if not isinstance(operating_systems, list) or not set(operating_systems).issubset({"linux", "windows"}):
            raise DefinitionValidationError(f"资源选择字段 {key} 的操作系统约束非法")
        min_count, max_count = binding.get("minCount"), binding.get("maxCount")
        if not isinstance(min_count, int) or not isinstance(max_count, int) or not 0 <= min_count <= max_count <= 100:
            raise DefinitionValidationError(f"资源选择字段 {key} 的数量约束非法")
        item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        if (
            schema.get("type") != "array"
            or item_schema.get("type") != "string"
            or schema.get("minItems") != min_count
            or schema.get("maxItems") != max_count
        ):
            raise DefinitionValidationError(f"资源选择字段 {key} 的 Schema 与数量约束不一致")
    elif widget == "file-upload":
        options = schema.get("x-file-options")
        if not isinstance(options, dict) or schema.get("type") != "object":
            raise DefinitionValidationError(f"文件字段 {key} 缺少上传配置")
        formats, modes = options.get("accept"), options.get("sourceModes")
        max_size = options.get("maxSizeMiB")
        if not isinstance(formats, list) or not formats or not set(formats).issubset(FILE_FORMATS):
            raise DefinitionValidationError(f"文件字段 {key} 的文件类型非法")
        if not isinstance(modes, list) or not modes or set(modes) != {"upload"}:
            raise DefinitionValidationError(f"文件字段 {key} 的来源非法")
        if isinstance(max_size, bool) or not isinstance(max_size, (int, float)) or not 0 < max_size <= 5 or options.get("maxCount") != 1:
            raise DefinitionValidationError(f"文件字段 {key} 的上传限额非法")
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        expected_kinds = ["uploaded"]
        if (properties.get("kind") or {}).get("enum") != expected_kinds:
            raise DefinitionValidationError(f"文件字段 {key} 的 Schema 与文件来源不一致")
        if (properties.get("format") or {}).get("enum") != formats:
            raise DefinitionValidationError(f"文件字段 {key} 的 Schema 与文件类型不一致")
        if (properties.get("size") or {}).get("maximum") != max_size * 1024 * 1024:
            raise DefinitionValidationError(f"文件字段 {key} 的 Schema 与上传限额不一致")


def _object_list(metadata: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = metadata.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise DefinitionValidationError(f"{key} 必须是对象数组")
    return value


def _validate_schema(schema: Any, *, node_id: str) -> dict[str, Any]:
    if not isinstance(schema, dict):
        raise DefinitionValidationError(f"触发节点 {node_id} 的 input_schema 必须是对象")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise DefinitionValidationError(f"触发节点 {node_id} 的 input_schema 非法") from error
    if schema.get("type") != "object":
        raise DefinitionValidationError(f"触发节点 {node_id} 的 input_schema 顶层必须是 object")
    return schema


def _reachable_returns(start: str, adjacency: dict[str, set[str]], return_ids: set[str]) -> set[str]:
    found: set[str] = set()
    pending = deque([start])
    visited = {start}
    while pending:
        current = pending.popleft()
        for target in adjacency.get(current, set()):
            if target in return_ids:
                found.add(target)
            elif target not in visited:
                visited.add(target)
                pending.append(target)
    return found


def _reachable_nodes(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    visited = {start}
    pending = deque([start])
    while pending:
        for target in adjacency.get(pending.popleft(), set()):
            if target not in visited:
                visited.add(target)
                pending.append(target)
    return visited


def validate_orchestration_metadata(  # noqa: C901
    canvas_metadata: Any,
    *,
    task_references: set[str],
) -> dict[str, Any]:
    """校验 BK-Lite 画布的触发/响应契约。

    历史版本没有 ``trigger_nodes`` 时保持原样，新画布一旦写入该字段就必须完整遵守 MVP 契约。
    """
    if not isinstance(canvas_metadata, dict):
        raise DefinitionValidationError("canvas_metadata 必须是 JSON 对象")
    metadata = copy.deepcopy(canvas_metadata)
    if "trigger_nodes" not in metadata:
        return metadata

    triggers = _object_list(metadata, "trigger_nodes")
    returns = _object_list(metadata, "return_nodes")
    edges = _object_list(metadata, "edges")
    if not 1 <= len(triggers) <= 10:
        raise DefinitionValidationError("流程必须包含 1 到 10 个触发节点")

    ids: set[str] = set(task_references)
    trigger_by_id: dict[str, dict[str, Any]] = {}
    for item in triggers:
        node_id = item.get("id")
        trigger_type = item.get("trigger_type")
        if not isinstance(node_id, str) or not NODE_ID.fullmatch(node_id) or node_id in ids:
            raise DefinitionValidationError("触发节点 ID 缺失、重复或非法")
        if trigger_type not in TRIGGER_TYPES:
            raise DefinitionValidationError(f"触发节点 {node_id} 类型非法")
        if trigger_type == "WEBHOOK":
            item["input_schema"] = webhook_input_schema()
        item["input_schema"] = _validate_schema(item.get("input_schema", {}), node_id=node_id)
        properties = item["input_schema"].get("properties", {})
        required = item["input_schema"].get("required", [])
        if not isinstance(properties, dict) or len(properties) > 50:
            raise DefinitionValidationError(f"触发节点 {node_id} 最多定义 50 个输入字段")
        if not isinstance(required, list) or not set(required).issubset(properties):
            raise DefinitionValidationError(f"触发节点 {node_id} 的 required 引用了不存在的字段")
        if any(not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) for key in properties):
            raise DefinitionValidationError(f"触发节点 {node_id} 的输入 key 非法")
        for key, schema in properties.items():
            if isinstance(schema, dict):
                _validate_form_field_extension(key, schema)
        config = item.get("config", {})
        if not isinstance(config, dict):
            raise DefinitionValidationError(f"触发节点 {node_id} 的 config 必须是对象")
        if trigger_type == "WEBHOOK" and config.get("response_mode", "IMMEDIATE") not in {"WAIT", "IMMEDIATE"}:
            raise DefinitionValidationError(f"Webhook 触发节点 {node_id} 响应模式非法")
        if trigger_type == "SCHEDULE":
            item["config"] = compile_schedule_config(config)
        if trigger_type == "NATS":
            if config:
                raise DefinitionValidationError(f"NATS 触发节点 {node_id} 不需要配置参数")
        ids.add(node_id)
        trigger_by_id[node_id] = item

    return_by_id: dict[str, dict[str, Any]] = {}
    for item in returns:
        node_id = item.get("id")
        if not isinstance(node_id, str) or not NODE_ID.fullmatch(node_id) or node_id in ids:
            raise DefinitionValidationError("Return 节点 ID 缺失、重复或非法")
        if item.get("return_type") not in RETURN_TYPES:
            raise DefinitionValidationError(f"Return 节点 {node_id} 类型非法")
        config = item.get("config", {})
        if not isinstance(config, dict):
            raise DefinitionValidationError(f"Return 节点 {node_id} 的 config 必须是对象")
        body = config.get("body")
        if item.get("return_type") == "WEBHOOK" and (
            not isinstance(body, str) or not re.fullmatch(r"\$\{[A-Za-z][A-Za-z0-9_-]{0,99}\.output(?:\.[^{}]+)?}", body.strip())
        ):
            raise DefinitionValidationError(f"Webhook 响应节点 {node_id} 必须选择一个完整结构化输出")
        ids.add(node_id)
        return_by_id[node_id] = item

    if len(ids) > 100:
        raise DefinitionValidationError("单个流程最多支持 100 个节点")

    adjacency: dict[str, set[str]] = defaultdict(set)
    indegree = {node_id: 0 for node_id in ids}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source not in ids or target not in ids or source == target:
            raise DefinitionValidationError("画布连线引用了不存在的节点或自环")
        if target not in adjacency[source]:
            adjacency[source].add(target)
            indegree[target] += 1

    if any(indegree[node_id] for node_id in trigger_by_id):
        raise DefinitionValidationError("触发节点不能有入边")
    return_ids = set(return_by_id)
    if any(adjacency.get(node_id) for node_id in return_ids):
        raise DefinitionValidationError("Return 节点不能有出边")

    pending = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while pending:
        current = pending.popleft()
        visited += 1
        for target in adjacency.get(current, set()):
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(target)
    if visited != len(ids):
        raise DefinitionValidationError("流程画布不能包含环")

    reachable_from_any_trigger: set[str] = set()
    for trigger_id, trigger in trigger_by_id.items():
        reachable_nodes = _reachable_nodes(trigger_id, adjacency)
        reachable_from_any_trigger.update(reachable_nodes)
        reachable = _reachable_returns(trigger_id, adjacency, return_ids)
        trigger_type = trigger["trigger_type"]
        requires_return = trigger_type == "WEBHOOK" and trigger["config"].get("response_mode", "IMMEDIATE") == "WAIT"
        allows_return = requires_return
        if not allows_return and reachable:
            raise DefinitionValidationError(f"{trigger_type} 触发路径禁止出现 Return")
        if requires_return and not reachable:
            raise DefinitionValidationError(f"{trigger_type} 触发路径必须到达对应 Return")
        if requires_return and len(reachable) != 1:
            raise DefinitionValidationError("等待模式 Webhook 触发路径必须且只能到达一个 Webhook 响应节点")
        incompatible = [node_id for node_id in reachable if return_by_id[node_id]["return_type"] != trigger_type]
        if incompatible:
            raise DefinitionValidationError(f"{trigger_type} 触发路径只能到达 {trigger_type} Return")
        terminal_nodes = {node_id for node_id in reachable_nodes if not adjacency.get(node_id)}
        if reachable and (not terminal_nodes or not terminal_nodes.issubset(reachable)):
            raise DefinitionValidationError(f"{trigger_type} 触发路径存在未连接到 Return 的结束节点")

    unreachable = ids.difference(reachable_from_any_trigger)
    if unreachable:
        raise DefinitionValidationError(f"存在未连接到任何触发器的节点: {', '.join(sorted(unreachable))}")

    # Internal validation index generated from trigger schemas. This is not an
    # editable workflow-parameter model; trigger nodes remain authoritative.
    previous = metadata.get("data_contract") if isinstance(metadata.get("data_contract"), dict) else {}
    previous_inputs = {item.get("key"): item for item in previous.get("inputs", []) if isinstance(item, dict) and isinstance(item.get("key"), str)}
    trigger_properties = [item["input_schema"].get("properties", {}) for item in triggers]
    common_keys = set(trigger_properties[0]) if trigger_properties else set()
    for properties in trigger_properties[1:]:
        common_keys.intersection_update(properties)
    common_keys = {key for key in common_keys if all(properties[key] == trigger_properties[0][key] for properties in trigger_properties[1:])}
    required_by_all = set.intersection(*(set(item["input_schema"].get("required", [])) for item in triggers)) if triggers else set()
    contract_inputs = []
    for order, key in enumerate(key for key in trigger_properties[0] if key in common_keys):
        schema = trigger_properties[0][key]
        old = previous_inputs.get(key, {})
        contract_item = {
            "parameterId": f"trigger:common:{key}",
            "key": key,
            "name": schema.get("title") or key,
            "schema": copy.deepcopy(schema),
            "required": key in required_by_all,
            "group": "basic",
            "order": order,
            "sensitive": bool(schema.get("sensitive")),
        }
        ui = copy.deepcopy(old.get("ui")) if isinstance(old.get("ui"), dict) else {}
        if isinstance(schema.get("x-widget"), str):
            ui["widget"] = schema["x-widget"]
        if isinstance(schema.get("x-target-binding"), dict):
            ui["targetBinding"] = copy.deepcopy(schema["x-target-binding"])
        if ui:
            contract_item["ui"] = ui
        if "default" in schema:
            contract_item["defaultValue"] = copy.deepcopy(schema["default"])
        contract_inputs.append(contract_item)
    metadata["data_contract"] = {
        "version": 1,
        "systemContextVersion": 1,
        "inputs": contract_inputs,
        "constants": [],
        "outputs": [],
    }
    metadata["input_schema"] = {
        "type": "object",
        "properties": {item["key"]: copy.deepcopy(item["schema"]) for item in contract_inputs},
        "required": [item["key"] for item in contract_inputs if item["required"]],
        "additionalProperties": False,
    }
    metadata["input_ui_schema"] = {
        item["key"]: {"ui:widget": item["ui"]["widget"]}
        for item in contract_inputs
        if isinstance(item.get("ui"), dict) and isinstance(item["ui"].get("widget"), str)
    }
    return metadata
