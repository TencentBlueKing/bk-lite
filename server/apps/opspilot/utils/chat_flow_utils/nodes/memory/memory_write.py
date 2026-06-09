"""
记忆写入节点 - 异步将内容写入记忆空间（透传输入）

作为支线节点存在，不影响主流程的输入输出。

记忆写入规则：
- 个人记忆：每个用户在每个记忆空间只有一条记忆，新内容与现有记忆合并
- 组织记忆：每个组织在每个记忆空间只有一条记忆，新内容与现有记忆合并

支持的存储引擎：
- local: 本地 PostgreSQL 存储
- mem0: Mem0 云服务
- zep: Zep 云服务
- custom: 自定义 API
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.memory.engines.base import MemoryEntity
from apps.opspilot.memory.engines.registry import MemoryEngineRegistry
from apps.opspilot.models.memory_mgmt import MemorySpace
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor


def build_memory_entity(memory_space: MemorySpace, user_id: str, flow_input: dict = None) -> MemoryEntity:
    """根据记忆空间 scope 构建 MemoryEntity

    Args:
        memory_space: 记忆空间对象
        user_id: 用户 ID（格式：username 或 username@domain）
        flow_input: 可选的 flow_input 上下文，用于覆盖团队记忆的 organization_id

    Returns:
        MemoryEntity: 记忆实体
    """
    if memory_space.scope == MemorySpace.SCOPE_PERSONAL:
        # 个人记忆：使用 user_id
        return MemoryEntity(user_id=user_id)
    else:
        # 团队记忆：优先使用 flow_input.team[0]，回退到 memory_space.team[0]
        fi_team = (flow_input or {}).get("team") or [] if isinstance(flow_input, dict) else []
        team_ids = fi_team if fi_team else (memory_space.team or [])
        organization_id = team_ids[0] if team_ids else None
        return MemoryEntity(organization_id=organization_id)


class MemoryWriteNode(BaseNodeExecutor):
    """记忆写入节点 - 触发异步写入任务，透传输入"""

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        output_key = config.get("outputParams", "last_message")
        # 支持两种字段名：memorySpace（前端表单）和 memory_space_id（旧格式）
        memory_space_id = config.get("memorySpace") or config.get("memory_space_id")
        title = config.get("title", "")
        # 获取节点级别的模型配置（可选，覆盖记忆空间默认模型）
        model_id = config.get("llmModel")
        write_batch_size = config.get("writeBatchSize") or config.get("write_batch_size")

        message = input_data.get(input_key, "")

        if memory_space_id and message:
            try:
                # 获取记忆空间
                memory_space = MemorySpace.objects.get(id=memory_space_id)

                # 从 variable_manager 获取原始 flow_input，提取 user_id / user_ids
                flow_input = {}
                if hasattr(self, "variable_manager") and self.variable_manager:
                    flow_input = self.variable_manager.get_variable("flow_input", {}) or {}

                user_id = flow_input.get("user_id", "") or input_data.get("user_id", "")
                if not user_id:
                    user_id = "system"

                # 当 flow_input.user_ids 非空且为个人记忆时，按干系人逐个写入
                user_ids = flow_input.get("user_ids") if isinstance(flow_input, dict) else None
                if memory_space.scope == MemorySpace.SCOPE_PERSONAL and user_ids:
                    target_users = list(user_ids)
                else:
                    target_users = [user_id]

                engine = MemoryEngineRegistry.get_engine(memory_space_id)
                for target_user in target_users:
                    entity = build_memory_entity(memory_space, target_user, flow_input)
                    result = engine.write(
                        entity=entity,
                        content=message,
                        title=title or f"自动记忆-{node_id}",
                        metadata={
                            "workflow_id": self.variable_manager.get_variable("flow_id", "") if self.variable_manager else "",
                            "node_id": node_id,
                            "write_batch_size": write_batch_size,
                        },
                        model_id=model_id,
                    )
                    if not result.success:
                        logger.warning(f"[MemoryWrite] 节点 {node_id} 写入失败 (user={target_user}): {result.message}")
            except MemorySpace.DoesNotExist:
                logger.error(f"[MemoryWrite] 节点 {node_id} 记忆空间不存在: memory_space_id={memory_space_id}")
            except ValueError as e:
                logger.error(f"[MemoryWrite] 节点 {node_id} 引擎错误: {e}")
            except Exception as e:
                logger.error(f"[MemoryWrite] 节点 {node_id} 触发写入任务失败: {e}", exc_info=True)
        else:
            logger.warning(f"[MemoryWrite] 节点 {node_id} 跳过写入: " f"memory_space_id={memory_space_id}, message_empty={not message}")

        # 透传输入，不影响主流程
        return {output_key: message}
