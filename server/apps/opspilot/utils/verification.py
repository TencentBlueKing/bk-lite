"""
执行后验证模块

在操作类工具执行后，自动调用验证工具检查操作是否生效。

验证规格可来源于：
1. 工具自身元数据：tool.metadata["verification"] = ToolVerificationSpec
2. VerificationConfig.overrides 覆盖
3. 全局注册表 VERIFICATION_REGISTRY

优先级：overrides > tool.metadata > VERIFICATION_REGISTRY
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from apps.opspilot.metis.llm.chain.entity import ToolVerificationSpec, VerificationConfig

logger = logging.getLogger("opspilot")

# ---------------------------------------------------------------------------
# 全局验证注册表（代码级默认映射）
# ---------------------------------------------------------------------------

VERIFICATION_REGISTRY: Dict[str, ToolVerificationSpec] = {
    # K8s 操作类工具
    "restart_pod": ToolVerificationSpec(
        verify_tool="get_pod_details",
        args_mapping={"pod_name": "pod_name", "namespace": "namespace"},
        delay_seconds=5.0,
        description="验证 Pod 重启后状态是否为 Running",
    ),
    "scale_resource": ToolVerificationSpec(
        verify_tool="get_resource_details",
        args_mapping={"resource_type": "resource_type", "name": "name", "namespace": "namespace"},
        delay_seconds=5.0,
        description="验证副本数是否已调整到目标值",
    ),
    "update_resource": ToolVerificationSpec(
        verify_tool="get_resource_details",
        args_mapping={"resource_type": "resource_type", "name": "name", "namespace": "namespace"},
        delay_seconds=3.0,
        description="验证资源是否已更新",
    ),
    "delete_resource": ToolVerificationSpec(
        verify_tool="query_resources",
        args_mapping={"resource_type": "resource_type", "namespace": "namespace"},
        delay_seconds=3.0,
        description="验证资源是否已被删除",
    ),
    "create_resource": ToolVerificationSpec(
        verify_tool="query_resources",
        args_mapping={"resource_type": "resource_type", "namespace": "namespace"},
        delay_seconds=3.0,
        description="验证资源是否已创建成功",
    ),
    # SSH 操作类工具
    "ssh_execute_command": ToolVerificationSpec(
        verify_tool="ssh_execute_command",
        args_mapping={"host": "host", "username": "username"},
        delay_seconds=1.0,
        description="验证命令执行结果是否符合预期",
    ),
}


def get_verification_spec(
    tool_name: str,
    tool_instance: Any,
    config: VerificationConfig,
) -> Optional[ToolVerificationSpec]:
    """
    获取工具的验证规格。

    优先级：config.overrides > tool.metadata > VERIFICATION_REGISTRY
    """
    # 1. 配置覆盖
    if tool_name in config.overrides:
        return config.overrides[tool_name]

    # 2. 工具自身元数据
    if tool_instance and hasattr(tool_instance, "metadata") and isinstance(tool_instance.metadata, dict):
        verify_meta = tool_instance.metadata.get("verification")
        if verify_meta:
            if isinstance(verify_meta, ToolVerificationSpec):
                return verify_meta
            elif isinstance(verify_meta, dict):
                return ToolVerificationSpec(**verify_meta)

    # 3. 全局注册表
    return VERIFICATION_REGISTRY.get(tool_name)


def build_verify_args(
    spec: ToolVerificationSpec,
    action_tool_args: Dict[str, Any],
) -> Dict[str, Any]:
    """根据 args_mapping 从操作工具的参数构建验证工具的参数。"""
    verify_args = {}
    for verify_param, action_param in spec.args_mapping.items():
        if action_param in action_tool_args:
            verify_args[verify_param] = action_tool_args[action_param]
    return verify_args


async def run_verification(
    spec: ToolVerificationSpec,
    action_tool_name: str,
    action_tool_args: Dict[str, Any],
    action_tool_result: str,
    available_tools: List[Any],
    config: VerificationConfig,
    runnable_config: Any = None,
) -> Dict[str, Any]:
    """
    执行验证流程。

    Returns:
        {
            "verified": True,  # 验证是否通过（由 LLM 判断时始终为 None，交给 LLM）
            "verify_tool": "get_pod_details",
            "verify_result": "...",  # 验证工具返回结果
            "attempts": 1,
            "description": "...",
        }
    """
    # 查找验证工具
    verify_tool = None
    for t in available_tools:
        if getattr(t, "name", "") == spec.verify_tool:
            verify_tool = t
            break

    if not verify_tool:
        logger.warning(f"验证工具 '{spec.verify_tool}' 未在可用工具中找到，跳过验证 (action_tool={action_tool_name})")
        return {
            "verified": None,
            "verify_tool": spec.verify_tool,
            "verify_result": f"验证工具 {spec.verify_tool} 不可用",
            "attempts": 0,
            "description": spec.description,
        }

    # 构建验证参数
    verify_args = build_verify_args(spec, action_tool_args)

    # 延迟等待
    if spec.delay_seconds > 0:
        logger.info(f"验证前等待 {spec.delay_seconds}s (action_tool={action_tool_name})")
        await asyncio.sleep(spec.delay_seconds)

    # 执行验证（带重试）
    last_result = None
    for attempt in range(1, config.max_verify_retries + 1):
        try:
            if hasattr(verify_tool, "ainvoke"):
                result = await verify_tool.ainvoke(verify_args, config=runnable_config)
            else:
                result = verify_tool.invoke(verify_args, config=runnable_config)

            last_result = str(result) if not isinstance(result, str) else result

            logger.info(
                f"验证完成 (action_tool={action_tool_name}, verify_tool={spec.verify_tool}, " f"attempt={attempt}, result_preview={last_result[:200]})"
            )
            return {
                "verified": None,  # 交给 LLM 判断
                "verify_tool": spec.verify_tool,
                "verify_result": last_result,
                "attempts": attempt,
                "description": spec.description,
            }

        except Exception as e:
            logger.warning(f"验证工具执行失败 (action_tool={action_tool_name}, verify_tool={spec.verify_tool}, " f"attempt={attempt}, error={e})")
            last_result = f"验证工具执行失败: {e}"
            if attempt < config.max_verify_retries:
                await asyncio.sleep(config.retry_delay_seconds)

    return {
        "verified": None,
        "verify_tool": spec.verify_tool,
        "verify_result": last_result,
        "attempts": config.max_verify_retries,
        "description": spec.description,
    }
