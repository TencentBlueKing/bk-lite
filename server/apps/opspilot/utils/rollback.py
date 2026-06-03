"""
操作回滚模块

在操作类工具执行前拍快照，验证失败后自动或提示回滚。

与 verification.py 协作：
    验证失败 → 触发回滚流程

回滚规格来源优先级：
1. RollbackConfig.overrides（配置级覆盖）
2. tool.metadata["rollback"]（工具元数据）
3. ROLLBACK_REGISTRY（代码级默认映射）
"""

import logging
from typing import Any, Dict, List, Optional

from apps.opspilot.metis.llm.chain.entity import RollbackConfig, ToolRollbackSpec

logger = logging.getLogger("opspilot")

# ---------------------------------------------------------------------------
# 全局回滚注册表（代码级默认映射）
# ---------------------------------------------------------------------------

ROLLBACK_REGISTRY: Dict[str, ToolRollbackSpec] = {
    "scale_deployment": ToolRollbackSpec(
        snapshot_tool="list_kubernetes_deployments",
        snapshot_args_mapping={"namespace": "namespace"},
        rollback_tool="scale_deployment",
        rollback_args_mapping={"deployment_name": "deployment_name", "namespace": "namespace"},
        rollback_snapshot_args={},  # replicas 需要从快照解析，在 _extract_snapshot_value 中处理
        strategy="prompt",
        description="回滚 Deployment 副本数到操作前的值",
    ),
    "delete_kubernetes_resource": ToolRollbackSpec(
        snapshot_tool=None,  # 删除操作无法自动回滚
        rollback_tool=None,
        strategy="none",
        description="资源删除不可自动回滚，需要手动重新创建",
    ),
    "restart_pod": ToolRollbackSpec(
        snapshot_tool=None,
        rollback_tool=None,
        strategy="none",
        description="Pod 重启不可回滚（由控制器重新调度）",
    ),
    "rollback_deployment": ToolRollbackSpec(
        snapshot_tool="get_deployment_revision_history",
        snapshot_args_mapping={"deployment_name": "deployment_name", "namespace": "namespace"},
        rollback_tool="rollback_deployment",
        rollback_args_mapping={"deployment_name": "deployment_name", "namespace": "namespace"},
        rollback_snapshot_args={},
        strategy="prompt",
        description="回滚操作本身可以通过再次回滚到之前的 revision 来撤销",
    ),
}


def get_rollback_spec(
    tool_name: str,
    tool_instance: Any,
    config: RollbackConfig,
) -> Optional[ToolRollbackSpec]:
    """
    获取工具的回滚规格。

    优先级：config.overrides > tool.metadata > ROLLBACK_REGISTRY
    """
    # 1. 配置覆盖
    if tool_name in config.overrides:
        return config.overrides[tool_name]

    # 2. 工具自身元数据
    if tool_instance and hasattr(tool_instance, "metadata") and isinstance(tool_instance.metadata, dict):
        rollback_meta = tool_instance.metadata.get("rollback")
        if rollback_meta:
            if isinstance(rollback_meta, ToolRollbackSpec):
                return rollback_meta
            elif isinstance(rollback_meta, dict):
                return ToolRollbackSpec(**rollback_meta)

    # 3. 全局注册表
    return ROLLBACK_REGISTRY.get(tool_name)


async def take_snapshot(
    spec: ToolRollbackSpec,
    action_tool_name: str,
    action_tool_args: Dict[str, Any],
    available_tools: List[Any],
    runnable_config: Any = None,
) -> Optional[str]:
    """
    操作前拍快照。

    Returns:
        快照结果字符串，None 表示无需快照或快照工具不可用。
    """
    if not spec.snapshot_tool:
        return None

    # 查找快照工具
    snapshot_tool = None
    for t in available_tools:
        if getattr(t, "name", "") == spec.snapshot_tool:
            snapshot_tool = t
            break

    if not snapshot_tool:
        logger.warning(f"快照工具 '{spec.snapshot_tool}' 未在可用工具中找到，跳过快照 (action_tool={action_tool_name})")
        return None

    # 构建快照参数
    snapshot_args = {}
    for snap_param, action_param in spec.snapshot_args_mapping.items():
        if action_param in action_tool_args:
            snapshot_args[snap_param] = action_tool_args[action_param]

    logger.info(f"拍快照: snapshot_tool={spec.snapshot_tool}, args={snapshot_args} (before {action_tool_name})")

    try:
        if hasattr(snapshot_tool, "ainvoke"):
            result = await snapshot_tool.ainvoke(snapshot_args, config=runnable_config)
        else:
            result = snapshot_tool.invoke(snapshot_args, config=runnable_config)
        snapshot_str = str(result) if not isinstance(result, str) else result
        logger.info(f"快照完成: action={action_tool_name}, snapshot_preview={snapshot_str[:300]}")
        return snapshot_str
    except Exception as e:
        logger.warning(f"快照失败: action={action_tool_name}, snapshot_tool={spec.snapshot_tool}, error={e}")
        return None


async def execute_rollback(
    spec: ToolRollbackSpec,
    action_tool_name: str,
    action_tool_args: Dict[str, Any],
    snapshot_result: Optional[str],
    available_tools: List[Any],
    runnable_config: Any = None,
) -> Dict[str, Any]:
    """
    执行回滚操作。

    Returns:
        {
            "rolled_back": bool,
            "rollback_tool": str or None,
            "rollback_result": str,
            "strategy": str,
            "description": str,
        }
    """
    if spec.strategy == "none":
        return {
            "rolled_back": False,
            "rollback_tool": None,
            "rollback_result": spec.description or "此操作不支持自动回滚",
            "strategy": "none",
            "description": spec.description,
        }

    if spec.strategy == "prompt" and not spec.rollback_tool:
        # 没有回滚工具，只能提示 LLM
        context = f"操作 {action_tool_name} 的验证失败。"
        if snapshot_result:
            context += f"\n操作前快照:\n{snapshot_result[:1000]}"
        context += f"\n{spec.description}"
        return {
            "rolled_back": False,
            "rollback_tool": None,
            "rollback_result": context,
            "strategy": "prompt",
            "description": spec.description,
        }

    if not spec.rollback_tool:
        return {
            "rolled_back": False,
            "rollback_tool": None,
            "rollback_result": "未配置回滚工具",
            "strategy": spec.strategy,
            "description": spec.description,
        }

    # 查找回滚工具
    rollback_tool = None
    for t in available_tools:
        if getattr(t, "name", "") == spec.rollback_tool:
            rollback_tool = t
            break

    if not rollback_tool:
        logger.warning(f"回滚工具 '{spec.rollback_tool}' 未在可用工具中找到 (action_tool={action_tool_name})")
        return {
            "rolled_back": False,
            "rollback_tool": spec.rollback_tool,
            "rollback_result": f"回滚工具 {spec.rollback_tool} 不可用",
            "strategy": spec.strategy,
            "description": spec.description,
        }

    # 构建回滚参数
    rollback_args = {}
    # 1. 从操作工具参数映射
    for rb_param, action_param in spec.rollback_args_mapping.items():
        if action_param in action_tool_args:
            rollback_args[rb_param] = action_tool_args[action_param]

    # 2. 从快照结果中提取（如果有）
    if snapshot_result and spec.rollback_snapshot_args:
        for rb_param, json_path in spec.rollback_snapshot_args.items():
            extracted = _extract_from_snapshot(snapshot_result, json_path)
            if extracted is not None:
                rollback_args[rb_param] = extracted

    logger.info(f"执行回滚: rollback_tool={spec.rollback_tool}, args={rollback_args} " f"(action={action_tool_name}, strategy={spec.strategy})")

    try:
        if hasattr(rollback_tool, "ainvoke"):
            result = await rollback_tool.ainvoke(rollback_args, config=runnable_config)
        else:
            result = rollback_tool.invoke(rollback_args, config=runnable_config)
        result_str = str(result) if not isinstance(result, str) else result
        logger.info(f"回滚完成: action={action_tool_name}, result_preview={result_str[:300]}")
        return {
            "rolled_back": True,
            "rollback_tool": spec.rollback_tool,
            "rollback_result": result_str,
            "strategy": spec.strategy,
            "description": spec.description,
        }
    except Exception as e:
        logger.error(f"回滚失败: action={action_tool_name}, rollback_tool={spec.rollback_tool}, error={e}")
        return {
            "rolled_back": False,
            "rollback_tool": spec.rollback_tool,
            "rollback_result": f"回滚执行失败: {e}",
            "strategy": spec.strategy,
            "description": spec.description,
        }


def _extract_from_snapshot(snapshot_str: str, json_path: str) -> Any:
    """
    从快照结果（JSON 字符串）中按 dot-path 提取值。

    例如 json_path="spec.replicas" 从 {"spec": {"replicas": 3}} 中提取 3。
    """
    try:
        import json_repair

        data = json_repair.loads(snapshot_str)
    except Exception:
        return None

    parts = json_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current
