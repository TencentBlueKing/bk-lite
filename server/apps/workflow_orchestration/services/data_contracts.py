from __future__ import annotations

import copy
import re
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from apps.core.mixinx import EncryptMixin
from apps.workflow_orchestration.services.capability_profiles import CapabilityProfileError, resolve_capability_input_schema
from apps.workflow_orchestration.services.definitions import DefinitionValidationError

PARAMETER_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
FULL_REFERENCE = re.compile(r"^\$\{([^{}]+)}$")
ANY_REFERENCE = re.compile(r"\$\{([^{}]+)}")
RESERVED_PREFIXES = ("system", "workflow", "node", "loop")
SYSTEM_CONTEXT_SCHEMA: dict[str, dict[str, Any]] = {
    "execution_id": {"type": "string"},
    "workflow_id": {"type": "string"},
    "workflow_version": {"type": "integer"},
    "organization_id": {"type": "string"},
    "trigger_id": {"type": "string"},
    "trigger_type": {"type": "string"},
    "actor_id": {"type": "string"},
    "actor_name": {"type": "string"},
    "started_at": {"type": "string"},
    "trace_id": {"type": "string"},
}
SECRET_ENVELOPE_PREFIX = "bklite-secret:v1:"


def _schema_type(schema: dict[str, Any] | None) -> str | None:
    value = (schema or {}).get("type")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return next((item for item in value if item != "null"), None)
    return None


def _nullable(schema: dict[str, Any] | None) -> bool:
    value = (schema or {}).get("type")
    return isinstance(value, list) and "null" in value


def _schema_at_path(schema: dict[str, Any] | None, path: list[str]) -> dict[str, Any] | None:
    current = schema
    for part in path:
        if not isinstance(current, dict):
            return None
        properties = current.get("properties")
        if isinstance(properties, dict) and isinstance(properties.get(part), dict):
            current = properties[part]
            continue
        additional = current.get("additionalProperties")
        if isinstance(additional, dict):
            current = additional
            continue
        return None
    return current


def _legacy_contract(metadata: dict[str, Any]) -> dict[str, Any]:
    input_schema = metadata.get("input_schema") if isinstance(metadata.get("input_schema"), dict) else {}
    properties = input_schema.get("properties") if isinstance(input_schema.get("properties"), dict) else {}
    required = input_schema.get("required") if isinstance(input_schema.get("required"), list) else []
    inputs = []
    for order, (key, schema) in enumerate(properties.items()):
        if not isinstance(schema, dict):
            schema = {}
        item = {
            "parameterId": f"input:{key}",
            "key": key,
            "name": schema.get("title") or key,
            "schema": copy.deepcopy(schema),
            "required": key in required,
            "group": "basic",
            "order": order,
            "sensitive": bool(schema.get("sensitive")),
        }
        if "default" in schema:
            item["defaultValue"] = copy.deepcopy(schema["default"])
        inputs.append(item)
    return {"version": 1, "systemContextVersion": 1, "inputs": inputs, "constants": [], "outputs": []}


def normalize_workflow_data_contract(canvas_metadata: Any) -> tuple[dict[str, Any], bool]:
    if not isinstance(canvas_metadata, dict):
        raise DefinitionValidationError("canvas_metadata 必须是 JSON 对象")
    metadata = copy.deepcopy(canvas_metadata)
    explicit = "data_contract" in metadata
    contract = metadata.get("data_contract") if explicit else _legacy_contract(metadata)
    if not isinstance(contract, dict):
        raise DefinitionValidationError("流程参数契约必须是 JSON 对象")
    metadata["data_contract"] = copy.deepcopy(contract)
    return metadata, explicit


def workflow_input_schema(contract: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for item in contract.get("inputs") or []:
        schema = copy.deepcopy(item.get("schema") or {})
        schema["title"] = item.get("name") or item.get("key")
        schema["sensitive"] = bool(item.get("sensitive"))
        if "defaultValue" in item:
            schema["default"] = copy.deepcopy(item["defaultValue"])
        properties[item["key"]] = schema
        if item.get("required"):
            required.append(item["key"])
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _validate_contract_shape(contract: dict[str, Any]) -> None:
    if contract.get("version") != 1 or contract.get("systemContextVersion") != 1:
        raise DefinitionValidationError("不支持的流程参数契约版本")
    for collection in ("inputs", "constants", "outputs"):
        if not isinstance(contract.get(collection), list):
            raise DefinitionValidationError(f"流程参数契约 {collection} 必须是数组")
    if contract["constants"] or contract["outputs"]:
        raise DefinitionValidationError("流程常量和流程输出已移除，请使用设置数据和对应的 Return 节点")
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for collection in ("inputs", "constants", "outputs"):
        for index, item in enumerate(contract[collection]):
            if not isinstance(item, dict):
                raise DefinitionValidationError(f"{collection}[{index}] 必须是对象")
            parameter_id = item.get("parameterId")
            key = item.get("key")
            if not isinstance(parameter_id, str) or not parameter_id or parameter_id in seen_ids:
                raise DefinitionValidationError(f"{collection}[{index}] 的 parameterId 缺失或重复")
            if not isinstance(key, str) or not PARAMETER_KEY.fullmatch(key):
                raise DefinitionValidationError(f"{collection}[{index}] 的 key 非法")
            if any(key == prefix or key.startswith(f"{prefix}_") for prefix in RESERVED_PREFIXES):
                raise DefinitionValidationError(f"参数 key 不能使用保留前缀: {key}")
            if key in seen_keys:
                raise DefinitionValidationError(f"参数 key 重复: {key}")
            schema = item.get("schema")
            if not isinstance(schema, dict):
                raise DefinitionValidationError(f"参数 {key} 缺少 Schema")
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as error:
                raise DefinitionValidationError(f"参数 {key} 的 Schema 非法") from error
            seen_ids.add(parameter_id)
            seen_keys.add(key)
    for item in contract["inputs"]:
        if item.get("group") not in {"basic", "advanced"}:
            raise DefinitionValidationError(f"流程输入 {item['key']} 的分组非法")
        if item.get("sensitive") and _schema_type(item["schema"]) != "string":
            raise DefinitionValidationError(f"敏感流程输入 {item['key']} 必须使用 string 类型")
        if item.get("sensitive") and "defaultValue" in item:
            raise DefinitionValidationError(f"敏感流程输入 {item['key']} 不能配置默认值")
        if "defaultValue" in item:
            errors = list(Draft202012Validator(item["schema"]).iter_errors(item["defaultValue"]))
            if errors:
                raise DefinitionValidationError(f"流程输入 {item['key']} 的默认值不符合 Schema")


def _collect_tasks(tasks: list[dict[str, Any]], inherited: list[str], task_map: dict[str, dict[str, Any]], reachable: dict[str, set[str]]) -> None:
    preceding = list(inherited)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        reference = task.get("taskReferenceName")
        if not isinstance(reference, str):
            continue
        if task.get("type") == "JOIN":
            for joined_reference in task.get("joinOn") or []:
                if not isinstance(joined_reference, str) or joined_reference not in task_map:
                    continue
                for dependency in [*reachable.get(joined_reference, set()), joined_reference]:
                    if dependency not in preceding:
                        preceding.append(dependency)
        task_map[reference] = task
        reachable[reference] = set(preceding)
        nested_inherited = [*preceding, reference]
        for branch in task.get("forkTasks") or []:
            if isinstance(branch, list):
                _collect_tasks(branch, nested_inherited, task_map, reachable)
        for branch in (task.get("decisionCases") or {}).values():
            if isinstance(branch, list):
                _collect_tasks(branch, nested_inherited, task_map, reachable)
        for key in ("defaultCase", "loopOver"):
            branch = task.get(key)
            if isinstance(branch, list):
                _collect_tasks(branch, nested_inherited, task_map, reachable)
        preceding.append(reference)


def _reference_schema(
    expression: str,
    *,
    contract: dict[str, Any],
    task_map: dict[str, dict[str, Any]],
    atom_catalog: dict[str, dict[str, Any]],
    current_reference: str | None,
    reachable: dict[str, set[str]],
) -> tuple[dict[str, Any], bool]:
    parts = expression.split(".")
    inputs = {item["key"]: item for item in contract["inputs"]}
    if len(parts) >= 3 and parts[:2] == ["workflow", "input"] and parts[2] in inputs:
        item = inputs[parts[2]]
        schema = _schema_at_path(item["schema"], parts[3:])
        if schema is None:
            raise DefinitionValidationError(f"数据引用不存在: {expression}")
        return schema, bool(item.get("sensitive") or schema.get("sensitive"))
    if len(parts) == 2 and parts[0] == "system" and parts[1] in SYSTEM_CONTEXT_SCHEMA:
        return SYSTEM_CONTEXT_SCHEMA[parts[1]], False
    if len(parts) >= 2 and parts[1] == "output" and parts[0] in task_map:
        source = parts[0]
        if current_reference is not None and source not in reachable.get(current_reference, set()):
            raise DefinitionValidationError(f"节点 {current_reference} 引用了当前路径不保证可用的输出: {source}")
        task = task_map[source]
        output_schema = (atom_catalog.get(task.get("name")) or {}).get("output_schema") or {}
        schema = _schema_at_path(output_schema, parts[2:])
        if schema is None:
            raise DefinitionValidationError(f"数据引用不存在: {expression}")
        return schema, bool(schema.get("sensitive"))
    raise DefinitionValidationError(f"数据引用不存在: {expression}")


def _validate_binding(
    value: Any,
    target_schema: dict[str, Any],
    *,
    contract: dict[str, Any],
    task_map: dict[str, dict[str, Any]],
    atom_catalog: dict[str, dict[str, Any]],
    current_reference: str,
    reachable: dict[str, set[str]],
) -> None:
    if isinstance(value, str):
        full = FULL_REFERENCE.fullmatch(value.strip())
        matches = list(ANY_REFERENCE.finditer(value))
        if full:
            source_schema, sensitive = _reference_schema(
                full.group(1),
                contract=contract,
                task_map=task_map,
                atom_catalog=atom_catalog,
                current_reference=current_reference,
                reachable=reachable,
            )
            source_type, target_type = _schema_type(source_schema), _schema_type(target_schema)
            compatible = source_type == target_type or (source_type == "integer" and target_type == "number")
            if target_type and not compatible:
                raise DefinitionValidationError(f"节点 {current_reference} 的引用类型 {source_type or 'unknown'} 不能绑定到 {target_type}")
            if sensitive and not target_schema.get("secretCompatible"):
                raise DefinitionValidationError(f"节点 {current_reference} 的目标字段不允许接收敏感值")
            return
        if matches:
            if _schema_type(target_schema) != "string":
                raise DefinitionValidationError(f"节点 {current_reference} 只能在 string 字段使用文本模板")
            for match in matches:
                source_schema, sensitive = _reference_schema(
                    match.group(1),
                    contract=contract,
                    task_map=task_map,
                    atom_catalog=atom_catalog,
                    current_reference=current_reference,
                    reachable=reachable,
                )
                if sensitive:
                    raise DefinitionValidationError(f"节点 {current_reference} 的文本模板不能使用敏感值")
                if _nullable(source_schema):
                    raise DefinitionValidationError(f"节点 {current_reference} 的文本模板不能使用可为 null 的值")
            return
    if isinstance(value, dict) and _schema_type(target_schema) == "object":
        properties = target_schema.get("properties") if isinstance(target_schema.get("properties"), dict) else {}
        for field in target_schema.get("required") or []:
            if field not in value:
                raise DefinitionValidationError(f"节点 {current_reference} 的对象字段缺少必填属性: {field}")
        for field, nested_value in value.items():
            nested_schema = properties.get(field)
            if isinstance(nested_schema, dict):
                _validate_binding(
                    nested_value,
                    nested_schema,
                    contract=contract,
                    task_map=task_map,
                    atom_catalog=atom_catalog,
                    current_reference=current_reference,
                    reachable=reachable,
                )
            elif _contains_sensitive_reference(
                nested_value,
                contract=contract,
                task_map=task_map,
                atom_catalog=atom_catalog,
                current_reference=current_reference,
                reachable=reachable,
            ):
                raise DefinitionValidationError(f"节点 {current_reference} 的未声明对象属性 {field} 不能接收敏感值")
        return
    if isinstance(value, list) and _schema_type(target_schema) == "array" and isinstance(target_schema.get("items"), dict):
        for nested_value in value:
            _validate_binding(
                nested_value,
                target_schema["items"],
                contract=contract,
                task_map=task_map,
                atom_catalog=atom_catalog,
                current_reference=current_reference,
                reachable=reachable,
            )
        return
    errors = list(Draft202012Validator(target_schema).iter_errors(value))
    if errors:
        raise DefinitionValidationError(f"节点 {current_reference} 的字面量不符合目标 Schema: {errors[0].message}")


def _replace_system_references(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\$\{system\.([a-z_]+)}", r"${workflow.input.__system.\1}", value)
    if isinstance(value, list):
        return [_replace_system_references(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_system_references(item) for key, item in value.items()}
    return value


def _contains_sensitive_reference(
    value: Any,
    *,
    contract: dict[str, Any],
    task_map: dict[str, dict[str, Any]],
    atom_catalog: dict[str, dict[str, Any]],
    current_reference: str,
    reachable: dict[str, set[str]],
) -> bool:
    if isinstance(value, str):
        for match in ANY_REFERENCE.finditer(value):
            try:
                _, sensitive = _reference_schema(
                    match.group(1),
                    contract=contract,
                    task_map=task_map,
                    atom_catalog=atom_catalog,
                    current_reference=current_reference,
                    reachable=reachable,
                )
            except DefinitionValidationError:
                continue
            if sensitive:
                return True
        return False
    if isinstance(value, list):
        return any(
            _contains_sensitive_reference(
                item,
                contract=contract,
                task_map=task_map,
                atom_catalog=atom_catalog,
                current_reference=current_reference,
                reachable=reachable,
            )
            for item in value
        )
    if isinstance(value, dict):
        return any(
            _contains_sensitive_reference(
                item,
                contract=contract,
                task_map=task_map,
                atom_catalog=atom_catalog,
                current_reference=current_reference,
                reachable=reachable,
            )
            for item in value.values()
        )
    return False


def _condition_operator(expression: str, index: int) -> str:
    if f"$.left_{index}.indexOf($.right_{index}) < 0" in expression:
        return "NOT_CONTAINS"
    if f"$.left_{index}.indexOf($.right_{index}) == 0" in expression:
        return "STARTS_WITH"
    if f"$.left_{index}.indexOf($.right_{index}) >= 0" in expression:
        return "CONTAINS"
    if f"$.left_{index}.slice($.left_{index}.length - $.right_{index}.length) == $.right_{index}" in expression:
        return "ENDS_WITH"
    match = re.search(rf"\$\.left_{index} (==|!=|>=|<=|>|<) \$\.right_{index}", expression)
    if not match:
        raise DefinitionValidationError("条件节点的结构化表达式非法")
    return match.group(1)


def _validate_condition_bindings(
    task: dict[str, Any],
    *,
    contract: dict[str, Any],
    task_map: dict[str, dict[str, Any]],
    atom_catalog: dict[str, dict[str, Any]],
    reachable: dict[str, set[str]],
) -> None:
    reference = task["taskReferenceName"]
    inputs = task.get("inputParameters") or {}
    expression = str(task.get("expression") or "")
    indexes = sorted(int(key.removeprefix("left_")) for key in inputs if re.fullmatch(r"left_\d+", key))
    for index in indexes:
        left = inputs[f"left_{index}"]
        match = FULL_REFERENCE.fullmatch(str(left).strip())
        if not match:
            raise DefinitionValidationError(f"条件节点 {reference} 左值必须是数据引用")
        left_schema, _ = _reference_schema(
            match.group(1),
            contract=contract,
            task_map=task_map,
            atom_catalog=atom_catalog,
            current_reference=reference,
            reachable=reachable,
        )
        operator = _condition_operator(expression, index)
        left_type = _schema_type(left_schema)
        if operator in {">", ">=", "<", "<="} and left_type not in {"integer", "number"}:
            raise DefinitionValidationError(f"条件节点 {reference} 的大小比较只支持数值类型")
        target_schema = left_schema
        if operator in {"CONTAINS", "NOT_CONTAINS"}:
            if left_type == "array" and isinstance(left_schema.get("items"), dict):
                target_schema = left_schema["items"]
            elif left_type != "string":
                raise DefinitionValidationError(f"条件节点 {reference} 的包含操作只支持字符串或数组")
        if operator in {"STARTS_WITH", "ENDS_WITH"} and left_type != "string":
            raise DefinitionValidationError(f"条件节点 {reference} 的开头/结尾操作只支持字符串")
        _validate_binding(
            inputs[f"right_{index}"],
            target_schema,
            contract=contract,
            task_map=task_map,
            atom_catalog=atom_catalog,
            current_reference=reference,
            reachable=reachable,
        )


def validate_and_compile_workflow_data_contract(
    definition: dict[str, Any],
    canvas_metadata: Any,
    *,
    atom_catalog: dict[str, dict[str, Any]],
    strict: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata, explicit = normalize_workflow_data_contract(canvas_metadata)
    contract = metadata["data_contract"]
    if not explicit:
        return copy.deepcopy(definition), metadata
    if not strict:
        return copy.deepcopy(definition), metadata
    _validate_contract_shape(contract)
    compiled = copy.deepcopy(definition)
    task_map: dict[str, dict[str, Any]] = {}
    reachable: dict[str, set[str]] = {}
    _collect_tasks(compiled.get("tasks") or [], [], task_map, reachable)
    for reference, task in task_map.items():
        inputs = task.get("inputParameters") if isinstance(task.get("inputParameters"), dict) else {}
        if task.get("type") != "SIMPLE":
            if _contains_sensitive_reference(
                inputs,
                contract=contract,
                task_map=task_map,
                atom_catalog=atom_catalog,
                current_reference=reference,
                reachable=reachable,
            ):
                raise DefinitionValidationError(f"敏感值不能用于控制流、审批或等待节点: {reference}")
            if task.get("type") == "SWITCH" and task.get("name") == "condition":
                _validate_condition_bindings(
                    task,
                    contract=contract,
                    task_map=task_map,
                    atom_catalog=atom_catalog,
                    reachable=reachable,
                )
            continue
        try:
            input_schema = resolve_capability_input_schema(atom_catalog.get(task.get("name")) or {}, inputs)
        except CapabilityProfileError as error:
            raise DefinitionValidationError(f"节点 {reference} {error}") from error
        properties = input_schema.get("properties") if isinstance(input_schema.get("properties"), dict) else {}
        for field in input_schema.get("required") or []:
            if field not in inputs:
                raise DefinitionValidationError(f"节点 {reference} 缺少必填输入: {field}")
        for field, value in inputs.items():
            target_schema = properties.get(field)
            if isinstance(target_schema, dict):
                _validate_binding(
                    value,
                    target_schema,
                    contract=contract,
                    task_map=task_map,
                    atom_catalog=atom_catalog,
                    current_reference=reference,
                    reachable=reachable,
                )
            elif _contains_sensitive_reference(
                value,
                contract=contract,
                task_map=task_map,
                atom_catalog=atom_catalog,
                current_reference=reference,
                reachable=reachable,
            ):
                raise DefinitionValidationError(f"节点 {reference} 的未声明字段 {field} 不能接收敏感值")
    metadata["input_schema"] = workflow_input_schema(contract)
    compiled["inputParameters"] = [*[item["key"] for item in contract["inputs"]], "execution_id", "team", "__system"]
    compiled["variables"] = {}
    compiled["outputParameters"] = {}
    compiled = _replace_system_references(compiled)
    return compiled, metadata


def redact_sensitive_inputs(inputs: dict[str, Any], canvas_metadata: Any) -> dict[str, Any]:
    metadata, _ = normalize_workflow_data_contract(canvas_metadata)
    sensitive_keys = {item.get("key") for item in metadata["data_contract"].get("inputs") or [] if isinstance(item, dict) and item.get("sensitive")}
    return {key: ("***" if key in sensitive_keys else copy.deepcopy(value)) for key, value in inputs.items()}


def seal_sensitive_inputs(inputs: dict[str, Any], canvas_metadata: Any) -> dict[str, Any]:
    metadata, _ = normalize_workflow_data_contract(canvas_metadata)
    sensitive_keys = {item.get("key") for item in metadata["data_contract"].get("inputs") or [] if isinstance(item, dict) and item.get("sensitive")}
    sealed = copy.deepcopy(inputs)
    cipher = EncryptMixin.get_cipher_suite()
    for key in sensitive_keys:
        if key not in sealed:
            continue
        value = sealed[key]
        if not isinstance(value, str):
            raise DefinitionValidationError(f"敏感流程输入 {key} 必须是字符串")
        sealed[key] = f"{SECRET_ENVELOPE_PREFIX}{cipher.encrypt(value.encode('utf-8')).decode('ascii')}"
    return sealed


def resolve_secret_envelopes(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(SECRET_ENVELOPE_PREFIX):
        token = value.removeprefix(SECRET_ENVELOPE_PREFIX)
        return EncryptMixin.get_cipher_suite().decrypt(token.encode("ascii")).decode("utf-8")
    if isinstance(value, list):
        return [resolve_secret_envelopes(item) for item in value]
    if isinstance(value, dict):
        return {key: resolve_secret_envelopes(item) for key, item in value.items()}
    return value


def mask_secret_envelopes(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(SECRET_ENVELOPE_PREFIX):
        return "***"
    if isinstance(value, list):
        return [mask_secret_envelopes(item) for item in value]
    if isinstance(value, dict):
        return {key: mask_secret_envelopes(item) for key, item in value.items()}
    return copy.deepcopy(value)
