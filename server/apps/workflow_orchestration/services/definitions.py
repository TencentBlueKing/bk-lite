from __future__ import annotations

import copy
import json
import re
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

MAX_DEFINITION_BYTES = 256 * 1024
SUPPORTED_SYSTEM_TASKS = {"FORK_JOIN", "JOIN", "SWITCH", "HUMAN"}
SUPPORTED_ATOMS = {
    "bklite_notification",
    "bklite_job_execute",
    "bklite_document_render",
    "bklite_http_request",
}
CONDUCTOR_REFERENCE = re.compile(r"^\$\{[^{}]+\}$")
ANY_CONDUCTOR_REFERENCE = re.compile(r"\$\{([^{}]+)}")
CONDITION_PART = (
    r"(?:\$\.left_\d+ (?:==|!=|>=|<=|>|<) \$\.right_\d+"
    r"|\$\.left_\d+\.indexOf\(\$\.right_\d+\) (?:>=|<|==) 0"
    r"|\$\.left_\d+\.slice\(\$\.left_\d+\.length - \$\.right_\d+\.length\) == \$\.right_\d+)"
)
STRUCTURED_CONDITION_EXPRESSION = re.compile(rf"^\((?P<parts>{CONDITION_PART}(?: (?:&&|\|\|) {CONDITION_PART})*)\) \? 'true' : 'false'$")
CONDITION_TERM = re.compile(
    r"(?:\$\.left_(\d+) (?:==|!=|>=|<=|>|<) \$\.right_(\d+)"
    r"|\$\.left_(\d+)\.indexOf\(\$\.right_(\d+)\) (?:>=|<|==) 0"
    r"|\$\.left_(\d+)\.slice\(\$\.left_(\d+)\.length - \$\.right_(\d+)\.length\) == \$\.right_(\d+))"
)


class DefinitionValidationError(ValueError):
    pass


def compile_disabled_nodes(definition: Any, canvas_metadata: Any) -> dict[str, Any]:
    """Build the executable definition while retaining disabled nodes in the authored draft."""
    if not isinstance(definition, dict):
        raise DefinitionValidationError("Conductor DSL 必须是 JSON 对象")
    if not isinstance(canvas_metadata, dict):
        raise DefinitionValidationError("canvas_metadata 必须是 JSON 对象")
    raw_disabled = canvas_metadata.get("disabled_nodes", [])
    if not isinstance(raw_disabled, list):
        raise DefinitionValidationError("disabled_nodes 必须是节点引用数组")
    if len(raw_disabled) > 100:
        raise DefinitionValidationError("单个流程最多停用 100 个节点")
    if not all(isinstance(reference, str) and reference.strip() for reference in raw_disabled):
        raise DefinitionValidationError("disabled_nodes 只能包含非空节点引用")
    disabled = set(raw_disabled)
    if len(disabled) != len(raw_disabled):
        raise DefinitionValidationError("disabled_nodes 不能包含重复节点引用")
    if not disabled:
        return copy.deepcopy(definition)

    task_map = {
        task.get("taskReferenceName"): task
        for task in _walk_tasks(definition.get("tasks") or [])
        if isinstance(task, dict) and isinstance(task.get("taskReferenceName"), str)
    }
    missing = sorted(disabled.difference(task_map))
    if missing:
        raise DefinitionValidationError(f"停用节点不存在: {', '.join(missing)}")
    invalid = sorted(reference for reference in disabled if task_map[reference].get("type") != "SIMPLE")
    if invalid:
        raise DefinitionValidationError(f"只有 SIMPLE 原子节点可以停用: {', '.join(invalid)}")

    def prune(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for original in tasks:
            if original.get("taskReferenceName") in disabled:
                continue
            task = copy.deepcopy(original)
            for key in ("loopOver", "defaultCase"):
                if isinstance(task.get(key), list):
                    task[key] = prune(task[key])
            if isinstance(task.get("decisionCases"), dict):
                task["decisionCases"] = {key: prune(branch) for key, branch in task["decisionCases"].items()}
            if isinstance(task.get("forkTasks"), list):
                task["forkTasks"] = [prune(branch) for branch in task["forkTasks"]]
            result.append(task)
        return result

    compiled = copy.deepcopy(definition)
    compiled["tasks"] = prune(compiled.get("tasks") or [])

    def referenced_disabled(value: Any, *, field_name: str = "") -> str | None:
        if isinstance(value, str):
            for match in ANY_CONDUCTOR_REFERENCE.finditer(value):
                reference = match.group(1).split(".", 1)[0]
                if reference in disabled:
                    return reference
            if field_name == "joinOn" and value in disabled:
                return value
        if isinstance(value, list):
            return next((found for item in value if (found := referenced_disabled(item, field_name=field_name))), None)
        if isinstance(value, dict):
            return next(
                (found for key, item in value.items() if (found := referenced_disabled(item, field_name=key))),
                None,
            )
        return None

    referenced = referenced_disabled(compiled)
    if referenced:
        raise DefinitionValidationError(f"停用节点 {referenced} 的输出仍被引用，请先调整下游配置")
    return compiled


def validate_workflow_inputs(inputs: Any, schema: Any) -> dict[str, Any]:
    if not isinstance(inputs, dict):
        raise DefinitionValidationError("inputs 必须是 JSON 对象")
    if len(json.dumps(inputs, ensure_ascii=False).encode("utf-8")) > 1024 * 1024:
        raise DefinitionValidationError("流程输入超过 1 MiB 限额")
    if not schema:
        return copy.deepcopy(inputs)
    if not isinstance(schema, dict):
        raise DefinitionValidationError("工作流输入 Schema 非法")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise DefinitionValidationError("工作流输入 Schema 非法") from error
    normalized_inputs = copy.deepcopy(inputs)
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    for key, field_schema in properties.items():
        if key not in normalized_inputs and isinstance(field_schema, dict) and "default" in field_schema:
            normalized_inputs[key] = copy.deepcopy(field_schema["default"])
    errors = sorted(Draft202012Validator(schema).iter_errors(normalized_inputs), key=lambda item: list(item.path))
    if errors:
        location = ".".join(str(item) for item in errors[0].path) or "inputs"
        raise DefinitionValidationError(f"流程输入不符合 Schema: {location}: {errors[0].message}")
    return normalized_inputs


def _walk_tasks(tasks: list[dict[str, Any]]):
    for task in tasks:
        yield task
        for key in ("loopOver", "defaultCase"):
            nested = task.get(key)
            if isinstance(nested, list):
                yield from _walk_tasks(nested)
        for branch in (task.get("decisionCases") or {}).values():
            if isinstance(branch, list):
                yield from _walk_tasks(branch)
        for branch in task.get("forkTasks", []) or []:
            if isinstance(branch, list):
                yield from _walk_tasks(branch)


def _maximum_task_depth(tasks: list[dict[str, Any]], depth: int = 1) -> int:
    maximum = depth if tasks else depth - 1
    for task in tasks:
        branches = [
            *(branch for branch in task.get("forkTasks", []) or [] if isinstance(branch, list)),
            *(branch for branch in (task.get("decisionCases") or {}).values() if isinstance(branch, list)),
        ]
        default_case = task.get("defaultCase")
        if isinstance(default_case, list):
            branches.append(default_case)
        for branch in branches:
            maximum = max(maximum, _maximum_task_depth(branch, depth + 1))
    return maximum


def _validate_approval_branches(tasks: list[dict[str, Any]]) -> None:
    for index, task in enumerate(tasks):
        inputs = task.get("inputParameters") if isinstance(task.get("inputParameters"), dict) else {}
        if task.get("type") == "HUMAN":
            reference = task.get("taskReferenceName")
            next_task = tasks[index + 1] if index + 1 < len(tasks) else None
            cases = next_task.get("decisionCases") if isinstance(next_task, dict) else None
            switch_inputs = next_task.get("inputParameters") if isinstance(next_task, dict) else None
            if (
                not isinstance(next_task, dict)
                or next_task.get("type") != "SWITCH"
                or not isinstance(cases, dict)
                or not {"true", "false"}.issubset(cases)
                or reference not in json.dumps(switch_inputs or {}, ensure_ascii=False)
            ):
                raise DefinitionValidationError(f"审批节点 {reference} 必须紧接包含 true/false 的决策分支")
            if inputs.get("timeoutSeconds") is not None and "timeout" not in cases:
                raise DefinitionValidationError(f"审批节点 {reference} 启用超时后必须连接 timeout 分支")
        for nested in task.get("forkTasks", []) or []:
            if isinstance(nested, list):
                _validate_approval_branches(nested)
        for nested in (task.get("decisionCases") or {}).values():
            if isinstance(nested, list):
                _validate_approval_branches(nested)
        for key in ("defaultCase", "loopOver"):
            nested = task.get(key)
            if isinstance(nested, list):
                _validate_approval_branches(nested)


def _validate_atom_inputs(task: dict[str, Any], atom_catalog: dict[str, dict[str, Any]]) -> None:
    from apps.workflow_orchestration.services.capability_profiles import CapabilityProfileError, resolve_capability_input_schema

    reference = task["taskReferenceName"]
    inputs = task.get("inputParameters") if isinstance(task.get("inputParameters"), dict) else {}
    try:
        schema = resolve_capability_input_schema(atom_catalog.get(task["name"]) or {}, inputs)
    except CapabilityProfileError as error:
        raise DefinitionValidationError(f"节点 {reference} {error}") from error
    missing = [field for field in schema.get("required", []) if field not in inputs]
    if missing:
        raise DefinitionValidationError(f"节点 {reference} 缺少必填输入: {', '.join(missing)}")
    for field, value in inputs.items():
        field_schema = (schema.get("properties") or {}).get(field)
        if not isinstance(field_schema, dict):
            continue
        if isinstance(value, str) and CONDUCTOR_REFERENCE.fullmatch(value.strip()):
            continue
        errors = sorted(Draft202012Validator(field_schema).iter_errors(value), key=lambda item: list(item.path))
        if errors:
            raise DefinitionValidationError(f"节点 {reference} 输入 {field} 不符合原子 Schema: {errors[0].message}")


def _validate_structured_condition(task: dict[str, Any]) -> None:
    reference = task["taskReferenceName"]
    inputs = task.get("inputParameters")
    expression = task.get("expression")
    if task.get("evaluatorType") != "javascript" or not isinstance(inputs, dict) or not isinstance(expression, str):
        raise DefinitionValidationError(f"条件节点 {reference} 必须使用结构化条件")
    match = STRUCTURED_CONDITION_EXPRESSION.fullmatch(expression)
    if not match:
        raise DefinitionValidationError(f"条件节点 {reference} 必须使用结构化条件，不支持自由表达式")
    separators = re.findall(r" (&&|\|\|) ", match.group("parts"))
    if separators and len(set(separators)) != 1:
        raise DefinitionValidationError(f"条件节点 {reference} 不能混用 ALL/ANY 规则")
    indexes = []
    for term in CONDITION_TERM.finditer(match.group("parts")):
        values = [int(value) for value in term.groups() if value is not None]
        if not values or len(set(values)) != 1:
            raise DefinitionValidationError(f"条件节点 {reference} 的结构化规则序号非法")
        indexes.append(values[0])
    if indexes != list(range(len(indexes))) or not 1 <= len(indexes) <= 10:
        raise DefinitionValidationError(f"条件节点 {reference} 的结构化规则序号非法")
    expected_keys = {f"{side}_{index}" for index in indexes for side in ("left", "right")}
    if set(inputs) != expected_keys or any(
        not isinstance(inputs[f"left_{index}"], str)
        or not CONDUCTOR_REFERENCE.fullmatch(inputs[f"left_{index}"].strip())
        or (
            isinstance(inputs[f"right_{index}"], str)
            and "${" in inputs[f"right_{index}"]
            and not CONDUCTOR_REFERENCE.fullmatch(inputs[f"right_{index}"].strip())
        )
        for index in indexes
    ):
        raise DefinitionValidationError(f"条件节点 {reference} 的结构化参数非法")


def validate_conductor_definition(  # noqa: C901
    definition: Any,
    *,
    atom_catalog: dict[str, dict[str, Any]] | None = None,
    strict_inputs: bool = True,
    allow_empty_tasks: bool = False,
) -> dict[str, Any]:
    if not isinstance(definition, dict):
        raise DefinitionValidationError("Conductor DSL 必须是 JSON 对象")
    try:
        size = len(json.dumps(definition, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as error:
        raise DefinitionValidationError("Conductor DSL 必须可序列化为 JSON") from error
    if size > MAX_DEFINITION_BYTES:
        raise DefinitionValidationError("Conductor DSL 超过 256 KiB 限额")
    tasks = definition.get("tasks")
    if not isinstance(tasks, list):
        raise DefinitionValidationError("Conductor DSL 至少需要一个 tasks 节点")
    if not tasks:
        if allow_empty_tasks:
            return copy.deepcopy(definition)
        raise DefinitionValidationError("Conductor DSL 至少需要一个 tasks 节点")
    if len(list(_walk_tasks(tasks))) > 100:
        raise DefinitionValidationError("单个流程最多支持 100 个节点")
    if _maximum_task_depth(tasks) > 5:
        raise DefinitionValidationError("控制结构嵌套深度最多为 5")
    if atom_catalog is None:
        from apps.workflow_orchestration.services.atoms import ATOM_CATALOG

        atom_catalog = ATOM_CATALOG
    supported_atoms = set(atom_catalog)
    references: set[str] = set()
    for task in _walk_tasks(tasks):
        if not isinstance(task, dict):
            raise DefinitionValidationError("tasks 中的节点必须是对象")
        name = task.get("name")
        reference = task.get("taskReferenceName")
        task_type = task.get("type")
        if not isinstance(name, str) or not name or not isinstance(reference, str) or not reference:
            raise DefinitionValidationError("每个节点必须包含 name 和 taskReferenceName")
        if reference in references:
            raise DefinitionValidationError(f"节点引用重复: {reference}")
        references.add(reference)
        if task_type == "SIMPLE" and name not in supported_atoms:
            raise DefinitionValidationError(f"不支持的原子: {name}")
        if task_type == "SIMPLE" and strict_inputs:
            _validate_atom_inputs(task, atom_catalog)
        if task_type != "SIMPLE" and task_type not in SUPPORTED_SYSTEM_TASKS:
            raise DefinitionValidationError(f"不支持的 Conductor 节点类型: {task_type}")
        if task_type == "HUMAN":
            inputs = task.get("inputParameters") if isinstance(task.get("inputParameters"), dict) else {}
            candidates = inputs.get("candidates")
            if (
                not isinstance(candidates, list)
                or not 1 <= len(candidates) <= 20
                or len(set(candidates)) != len(candidates)
                or not all(isinstance(candidate, str) and candidate.strip() for candidate in candidates)
            ):
                raise DefinitionValidationError(f"审批节点 {reference} 必须配置 1 到 20 个不重复候选审批人")
            if not str(inputs.get("title") or "").strip():
                raise DefinitionValidationError(f"审批节点 {reference} 必须配置标题")
        if task_type == "FORK_JOIN":
            branches = task.get("forkTasks")
            if not isinstance(branches, list) or not 2 <= len(branches) <= 10 or not all(isinstance(branch, list) and branch for branch in branches):
                raise DefinitionValidationError(f"并行节点 {reference} 必须包含 2 到 10 个非空分支")
        if task_type == "JOIN":
            join_on = task.get("joinOn")
            if not isinstance(join_on, list) or not join_on or not all(isinstance(item, str) and item for item in join_on):
                raise DefinitionValidationError(f"汇聚节点 {reference} 必须配置 joinOn")
        if task_type == "SWITCH":
            cases = task.get("decisionCases")
            if not isinstance(cases, dict) or not 1 <= len(cases) <= 10:
                raise DefinitionValidationError(f"条件节点 {reference} 必须包含 1 到 10 个分支")
            if name == "condition":
                _validate_structured_condition(task)
    _validate_approval_branches(tasks)
    return copy.deepcopy(definition)


def prepare_definition_for_publish(
    definition: dict[str, Any],
    *,
    engine_name: str,
    version: int,
    atom_catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    published = validate_conductor_definition(definition, atom_catalog=atom_catalog)
    published["name"] = engine_name
    published["version"] = version
    published["schemaVersion"] = 2
    published["ownerEmail"] = "bklite@weops.com"
    _escape_literal_conductor_expressions(published)
    return published


# Conductor 把未转义的 ${...} 当成工作流引用；literal-only 字段（如脚本正文）必须写成 $${...}。
_LITERAL_INPUT_KEYS = frozenset(
    {
        "script_content",
        "execution_params",
        "body",
        "title",
        "url",
        "method",
        "headers",
        "payload",
    }
)


def escape_conductor_literal_text(value: str) -> str:
    """Escape bare ${...} so Conductor treats them as literals ($${...})."""
    if "${" not in value:
        return value
    return re.sub(r"(?<!\$)\$\{", "$${", value)


def _escape_literal_conductor_expressions(definition: dict[str, Any]) -> None:
    for task in _walk_tasks(definition.get("tasks") or []):
        if not isinstance(task, dict):
            continue
        inputs = task.get("inputParameters")
        if not isinstance(inputs, dict):
            continue
        for key in _LITERAL_INPUT_KEYS:
            raw = inputs.get(key)
            if isinstance(raw, str) and "${" in raw:
                inputs[key] = escape_conductor_literal_text(raw)


def build_blank_definition() -> dict[str, Any]:
    """Return an editable draft with no implicit workflow nodes."""
    return {
        "name": "workflow_draft",
        "description": "",
        "version": 1,
        "schemaVersion": 2,
        "ownerEmail": "bklite@weops.com",
        "inputParameters": [],
        "outputParameters": {},
        "tasks": [],
        "restartable": True,
        "workflowStatusListenerEnabled": False,
    }


def build_blank_canvas_metadata() -> dict[str, Any]:
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    return {
        "control_flow_mode": "EDGES",
        "trigger_nodes": [],
        "return_nodes": [],
        "edges": [],
        "input_schema": copy.deepcopy(input_schema),
        "data_contract": {
            "version": 1,
            "systemContextVersion": 1,
            "inputs": [],
            "constants": [],
            "outputs": [],
        },
        "risk_summary": {
            "level": "low",
            "description": "空白流程，尚未添加节点。",
        },
    }


def build_health_inspection_definition() -> dict[str, Any]:
    return {
        "name": "health_inspection_draft",
        "description": "主机健康巡检：选择目标主机，按发布版本中的脚本和模板生成报告并通知",
        "version": 1,
        "schemaVersion": 2,
        "ownerEmail": "bklite@weops.com",
        "inputParameters": ["targets", "team", "actor", "execution_id"],
        "outputParameters": {},
        "tasks": [
            {
                "name": "bklite_job_execute",
                "taskReferenceName": "scan",
                "type": "SIMPLE",
                "inputParameters": {
                    "targets": "${workflow.input.targets}",
                    "script_type": "shell",
                    "script_content": "",
                    "execution_params": "",
                    "timeout_seconds": 600,
                    "team": "${workflow.input.team}",
                    "actor": "${workflow.input.actor}",
                    "execution_id": "${workflow.input.execution_id}",
                },
            },
            {
                "name": "bklite_document_render",
                "taskReferenceName": "report",
                "type": "SIMPLE",
                "inputParameters": {
                    "data": "${scan.output}",
                    "execution_id": "${workflow.input.execution_id}",
                    "team": "${workflow.input.team}",
                },
            },
            {
                "name": "bklite_notification",
                "taskReferenceName": "notify",
                "type": "SIMPLE",
                "inputParameters": {
                    "notification_type": "EMAIL",
                    "channel_id": 1,
                    "recipients": [],
                    "title": "主机健康巡检报告",
                    "body": "主机健康巡检已完成。",
                    "report_artifact": "${report.output.artifact}",
                    "team": "${workflow.input.team}",
                    "execution_id": "${workflow.input.execution_id}",
                },
            },
        ],
        "restartable": True,
        "workflowStatusListenerEnabled": False,
    }


def build_health_inspection_canvas_metadata() -> dict[str, Any]:
    target_schema = {
        "type": "array",
        "title": "目标主机",
        "items": {
            "type": "string",
            "pattern": r"^(node:[^:]+|manual:[0-9]+)$",
        },
        "minItems": 1,
        "maxItems": 100,
        "uniqueItems": True,
        "x-widget": "target-selector",
        "x-target-binding": {
            "mode": "runtime",
            "allowedSources": ["node_mgmt", "job_mgmt"],
            "allowedOperatingSystems": ["linux", "windows"],
            "minCount": 1,
            "maxCount": 100,
        },
    }
    input_properties = {
        "targets": copy.deepcopy(target_schema),
    }
    return {
        "control_flow_mode": "EDGES",
        "trigger_nodes": [
            {
                "id": "trigger_form",
                "name": "健康巡检表单",
                "trigger_type": "FORM",
                "input_schema": {
                    "type": "object",
                    "properties": copy.deepcopy(input_properties),
                    "required": ["targets"],
                    "additionalProperties": False,
                },
                "config": {},
            }
        ],
        "return_nodes": [],
        "edges": [
            {"id": "trigger-scan", "source": "trigger_form", "target": "scan"},
            {"id": "scan-report", "source": "scan", "target": "report"},
            {"id": "report-notify", "source": "report", "target": "notify"},
        ],
        "input_schema": {
            "type": "object",
            "properties": copy.deepcopy(input_properties),
            "required": ["targets"],
            "additionalProperties": False,
        },
        "input_ui_schema": {
            "targets": {"ui:widget": "target-selector"},
        },
        "data_contract": {
            "version": 1,
            "systemContextVersion": 1,
            "inputs": [
                {
                    "parameterId": "input:targets",
                    "key": "targets",
                    "name": "目标主机",
                    "schema": copy.deepcopy(target_schema),
                    "required": True,
                    "group": "basic",
                    "order": 0,
                    "sensitive": False,
                    "ui": {
                        "widget": "target-selector",
                        "targetBinding": {
                            "mode": "runtime",
                            "allowedSources": ["node_mgmt", "job_mgmt"],
                            "allowedOperatingSystems": ["linux", "windows"],
                            "minCount": 1,
                            "maxCount": 100,
                        },
                    },
                },
            ],
            "constants": [],
            "outputs": [],
        },
        "risk_summary": {
            "level": "low",
            "description": "在授权主机上执行只读健康采集并生成巡检报告。",
        },
    }
