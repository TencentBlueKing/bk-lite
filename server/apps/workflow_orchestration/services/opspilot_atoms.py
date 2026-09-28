from __future__ import annotations

import copy
from typing import Any

from django.apps import apps as django_apps

from apps.core.utils.viewset_utils import build_json_membership_query
from apps.workflow_orchestration.services.agent_knowledge_inputs import resolve_uploaded_agent_knowledge

MAX_AGENT_OUTPUT_CHARS = 100_000
MAX_MEMORY_CONTEXT_CHARS = 100_000


def _trusted_context(inputs: dict[str, Any]) -> dict[str, Any]:
    context = inputs.get("__bklite_context")
    if not isinstance(context, dict):
        raise ValueError("缺少可信的流程执行上下文")
    try:
        organization_id = int(context.get("organization_id"))
    except (TypeError, ValueError) as error:
        raise ValueError("流程执行组织非法") from error
    actor = context.get("actor")
    if organization_id <= 0 or not isinstance(actor, dict):
        raise ValueError("流程执行身份非法")
    username = str(actor.get("username") or "").strip()
    domain = str(actor.get("domain") or "").strip()
    if not username or len(username) > 150 or len(domain) > 100:
        raise ValueError("流程执行身份非法")
    return {
        **context,
        "organization_id": organization_id,
        "actor": {"username": username, "domain": domain},
        "user_id": f"{username}@{domain}" if domain else username,
    }


def _opspilot_models():
    if not django_apps.is_installed("apps.opspilot"):
        raise ValueError("OpsPilot 应用未启用")
    from apps.opspilot.models import LLMModel, LLMSkill, MemorySpace

    return LLMModel, LLMSkill, MemorySpace


def _scoped_model(model_id: Any, organization_id: int):
    LLMModel, _, _ = _opspilot_models()
    queryset = LLMModel.objects.filter(enabled=True)
    model = queryset.filter(
        build_json_membership_query(queryset, "team", [organization_id]),
        pk=model_id,
    ).first()
    if model is None:
        raise ValueError("指定模型在当前组织不可用")
    return model


def _scoped_skill(skill_id: Any, organization_id: int):
    _, LLMSkill, _ = _opspilot_models()
    queryset = LLMSkill.objects.filter(is_template=False, llm_model__isnull=False, llm_model__enabled=True)
    skill = queryset.filter(
        build_json_membership_query(queryset, "usage_team", [organization_id]),
        pk=skill_id,
    ).first()
    if skill is None or not skill.team:
        raise ValueError("指定智能体在当前组织不可用")
    return skill


def _scoped_memory_space(space_id: Any, organization_id: int):
    _, _, MemorySpace = _opspilot_models()
    queryset = MemorySpace.objects.all()
    space = queryset.filter(
        build_json_membership_query(queryset, "team", [organization_id]),
        pk=space_id,
    ).first()
    if space is None:
        raise ValueError("指定记忆空间在当前组织不可用")
    return space


def _variable_manager(context: dict[str, Any], inputs: dict[str, Any]):
    from apps.opspilot.utils.chat_flow_utils.engine.core.variable_manager import VariableManager

    manager = VariableManager()
    flow_input = {
        "user_id": context["user_id"],
        "team": context["organization_id"],
        "execution_id": str(context.get("execution_id") or ""),
        "entry_type": "workflow_orchestration",
        "trigger_type": str(context.get("trigger_type") or ""),
    }
    manager.set_variable("flow_input", flow_input)
    manager.set_variable("flow_id", str(context.get("workflow_id") or ""))
    manager.set_variable("execution_id", str(context.get("execution_id") or ""))
    memory_context = inputs.get("memory_context")
    if isinstance(memory_context, str) and memory_context:
        manager.set_variable("memory_context", memory_context[:MAX_MEMORY_CONTEXT_CHARS])
    return manager


def _clean_text(value: Any, *, label: str, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label}必须是字符串")
    result = value.strip()
    if (required and not result) or len(result) > maximum:
        raise ValueError(f"{label}超出限额")
    return result


def execute_agent(inputs: dict[str, Any]) -> dict[str, Any]:
    from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode

    context = _trusted_context(inputs)
    skill = _scoped_skill(inputs.get("agent_id"), context["organization_id"])
    message = _clean_text(inputs.get("message"), label="message", maximum=50_000)
    prompt = _clean_text(inputs.get("prompt", ""), label="prompt", maximum=10_000, required=False)
    uploaded_files = resolve_uploaded_agent_knowledge(
        inputs.get("knowledge_files"),
        workflow_id=context.get("workflow_id"),
        team=context["organization_id"],
    )
    manager = _variable_manager(context, inputs)
    result = AgentNode(manager).execute(
        "workflow_agent",
        {
            "data": {
                "config": {
                    "agent": skill.id,
                    "prompt": prompt,
                    "uploadedFiles": uploaded_files,
                    "inputParams": "message",
                    "outputParams": "message",
                }
            }
        },
        {"message": message},
    )
    if not isinstance(result, dict) or result.get("success") is False:
        error_type = str((result or {}).get("error_type") or "AgentExecutionError") if isinstance(result, dict) else "AgentExecutionError"
        raise ValueError(f"智能体执行失败: {error_type[:100]}")
    output = result.get("message")
    if not isinstance(output, str):
        raise ValueError("智能体返回结果非法")
    return {"message": output[:MAX_AGENT_OUTPUT_CHARS]}


def execute_intent_classification(inputs: dict[str, Any]) -> dict[str, Any]:
    from apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier import IntentClassifierNode

    context = _trusted_context(inputs)
    model = _scoped_model(inputs.get("model_id"), context["organization_id"])
    text = _clean_text(inputs.get("text"), label="text", maximum=50_000)
    raw_intents = inputs.get("intents")
    if (
        not isinstance(raw_intents, list)
        or not 1 <= len(raw_intents) <= 20
        or not all(isinstance(item, str) and item.strip() and len(item.strip()) <= 80 for item in raw_intents)
    ):
        raise ValueError("intents 必须包含 1 到 20 个意图")
    intents = list(dict.fromkeys(item.strip() for item in raw_intents))
    if len(intents) != len(raw_intents):
        raise ValueError("intents 不能重复")
    rules = _clean_text(
        inputs.get("classification_rules", ""),
        label="classification_rules",
        maximum=5_000,
        required=False,
    )
    result = IntentClassifierNode(_variable_manager(context, inputs)).execute(
        "workflow_intent_classification",
        {
            "data": {
                "config": {
                    "llmModel": model.id,
                    "classificationRules": rules,
                    "intents": [{"name": item} for item in intents],
                    "inputParams": "text",
                    "outputParams": "intent",
                }
            }
        },
        {"text": text},
    )
    if not isinstance(result, dict) or result.get("success") is False:
        error_type = str((result or {}).get("error_type") or "IntentClassificationError") if isinstance(result, dict) else "IntentClassificationError"
        raise ValueError(f"意图分类失败: {error_type[:100]}")
    intent = result.get("intent_result")
    if intent not in intents:
        raise ValueError("意图分类返回了未声明的意图")
    return {"intent": intent, "text": text}


def _memory_entity(space, context: dict[str, Any]):
    from apps.opspilot.memory.engines.base import MemoryEntity

    if space.scope == space.SCOPE_PERSONAL:
        return MemoryEntity(user_id=context["user_id"])
    return MemoryEntity(organization_id=context["organization_id"])


def execute_memory_read(inputs: dict[str, Any]) -> dict[str, Any]:
    from apps.opspilot.memory.engines.registry import MemoryEngineRegistry

    context = _trusted_context(inputs)
    space = _scoped_memory_space(inputs.get("memory_space_id"), context["organization_id"])
    query = _clean_text(inputs.get("query"), label="query", maximum=20_000)
    top_k = inputs.get("top_k", 5)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 20:
        raise ValueError("top_k 必须在 1 到 20 之间")
    result = MemoryEngineRegistry.get_engine(space.id).read(
        entity=_memory_entity(space, context),
        query=query,
        top_k=top_k,
    )
    memory_context = result.context if isinstance(result.context, str) else ""
    raw_memories = result.raw_memories if isinstance(result.raw_memories, list) else []
    return {
        "query": query,
        "memory_context": memory_context[:MAX_MEMORY_CONTEXT_CHARS],
        "count": min(len(raw_memories), top_k),
        "source": str(result.source or "")[:50],
    }


def execute_memory_write(inputs: dict[str, Any]) -> dict[str, Any]:
    from apps.opspilot.memory.engines.registry import MemoryEngineRegistry

    context = _trusted_context(inputs)
    space = _scoped_memory_space(inputs.get("memory_space_id"), context["organization_id"])
    content = _clean_text(inputs.get("content"), label="content", maximum=50_000)
    title = _clean_text(inputs.get("title", ""), label="title", maximum=255, required=False)
    model_id = inputs.get("model_id")
    if model_id is not None:
        model_id = _scoped_model(model_id, context["organization_id"]).id
    write_batch_size = inputs.get("write_batch_size", 30)
    if isinstance(write_batch_size, bool) or not isinstance(write_batch_size, int) or not 1 <= write_batch_size <= 500:
        raise ValueError("write_batch_size 必须在 1 到 500 之间")
    result = MemoryEngineRegistry.get_engine(space.id).write(
        entity=_memory_entity(space, context),
        content=content,
        title=title or "编排流程记忆",
        metadata={
            "workflow_id": str(context.get("workflow_id") or ""),
            "execution_id": str(context.get("execution_id") or ""),
            "write_batch_size": write_batch_size,
        },
        model_id=model_id,
    )
    if not result.success:
        raise ValueError("记忆写入失败")
    return {
        "content": content,
        "written": True,
        "memory_id": result.memory_id,
        "event_id": result.event_id,
    }


def _enum_field(
    catalog: dict[str, dict[str, Any]],
    atom_key: str,
    field_key: str,
    rows: list[tuple[int, str]],
    *,
    metadata: dict[str, dict[str, Any]] | None = None,
) -> None:
    atom = catalog.get(atom_key)
    if atom is None:
        return
    schema = copy.deepcopy(atom.get("input_schema") or {})
    field = (schema.get("properties") or {}).get(field_key)
    if not isinstance(field, dict):
        return
    field["enum"] = [row_id for row_id, _ in rows]
    field["x-enum-labels"] = {str(row_id): name for row_id, name in rows}
    if metadata:
        field["x-enum-metadata"] = metadata
    atom["input_schema"] = schema


def materialize_opspilot_options(catalog: dict[str, dict[str, Any]], organization_id: int) -> None:
    """为设计器材料化当前组织可用的 OpsPilot 资源；执行时仍重新校验归属。"""
    if not django_apps.is_installed("apps.opspilot"):
        return
    LLMModel, LLMSkill, MemorySpace = _opspilot_models()
    models = LLMModel.objects.filter(enabled=True)
    models = models.filter(build_json_membership_query(models, "team", [organization_id])).order_by("name", "id")
    skills = LLMSkill.objects.filter(is_template=False, llm_model__isnull=False, llm_model__enabled=True)
    skills = skills.filter(build_json_membership_query(skills, "usage_team", [organization_id])).order_by("name", "id")
    spaces = MemorySpace.objects.all()
    spaces = spaces.filter(build_json_membership_query(spaces, "team", [organization_id])).order_by("name", "id")
    model_rows = list(models.values_list("id", "name"))
    skill_rows = list(skills.values_list("id", "name"))
    space_options = list(spaces.values_list("id", "name", "scope", "default_model"))
    space_rows = [(space_id, name) for space_id, name, _, _ in space_options]
    space_metadata = {str(space_id): {"scope": scope, "default_model": default_model} for space_id, _, scope, default_model in space_options}
    _enum_field(catalog, "bklite_agent", "agent_id", skill_rows)
    _enum_field(catalog, "bklite_intent_classification", "model_id", model_rows)
    _enum_field(catalog, "bklite_memory_read", "memory_space_id", space_rows, metadata=space_metadata)
    _enum_field(catalog, "bklite_memory_write", "memory_space_id", space_rows, metadata=space_metadata)
    _enum_field(catalog, "bklite_memory_write", "model_id", model_rows)
