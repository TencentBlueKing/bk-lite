"""
记忆写入节点 - 异步将内容写入记忆空间（透传输入）

作为支线节点存在，不影响主流程的输入输出。

记忆写入规则：
- 个人记忆：每个用户在每个记忆空间只有一条记忆，新内容与现有记忆合并
- 组织记忆：每个组织在每个记忆空间只有一条记忆，新内容与现有记忆合并
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor


class MemoryWriteNode(BaseNodeExecutor):
    """记忆写入节点 - 触发异步写入任务，透传输入"""

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        output_key = config.get("outputParams", "last_message")
        # 支持两种字段名：memorySpace（前端表单）和 memory_space_id（旧格式）
        memory_space_id = config.get("memorySpace") or config.get("memory_space_id")
        title = config.get("title", "")

        message = input_data.get(input_key, "")
        logger.info(f"[MemoryWrite] 节点 {node_id} 开始执行: memory_space_id={memory_space_id}, title={title}, input_key={input_key}")
        logger.info(f"[MemoryWrite] 节点 {node_id} 输入数据 keys: {list(input_data.keys())}")
        logger.info(f"[MemoryWrite] 节点 {node_id} 消息内容: {message[:100] if message else '(空)'}")

        if memory_space_id and message:
            try:
                from apps.opspilot.models.memory_mgmt import MemorySpace
                from apps.opspilot.tasks import process_memory_write

                # 获取记忆空间，判断 scope
                memory_space = MemorySpace.objects.get(id=memory_space_id)
                scope = memory_space.scope

                # 从 variable_manager 获取原始 flow_input，提取 user_id
                flow_input = {}
                if hasattr(self, "variable_manager") and self.variable_manager:
                    flow_input = self.variable_manager.get_variable("flow_input", {}) or {}

                user_id = flow_input.get("user_id", "") or input_data.get("user_id", "")
                if "@" in user_id:
                    username, domain = user_id.rsplit("@", 1)
                else:
                    username = user_id or "system"
                    domain = ""

                # 根据 scope 决定记忆归属
                if scope == MemorySpace.SCOPE_PERSONAL:
                    # 个人记忆：归属到当前用户
                    owner_username = username
                    owner_domain = domain
                    organization_id = None
                    organization_name = None
                    logger.info(f"[MemoryWrite] 节点 {node_id} 个人记忆，归属用户: {owner_username}@{owner_domain}")
                else:
                    # 组织记忆：归属到记忆空间所属的组织
                    # memory_space.team 是组织 ID 列表，取第一个作为主组织
                    team_ids = memory_space.team or []
                    organization_id = team_ids[0] if team_ids else None

                    # 获取组织名称
                    organization_name = None
                    if organization_id:
                        try:
                            from apps.system_mgmt.models import Group

                            group = Group.objects.get(id=organization_id)
                            organization_name = group.name
                        except Exception as e:
                            logger.warning(f"[MemoryWrite] 节点 {node_id} 获取组织名称失败: {e}")
                            organization_name = f"组织-{organization_id}"

                    owner_username = organization_name or f"组织-{organization_id}"
                    owner_domain = ""
                    logger.info(f"[MemoryWrite] 节点 {node_id} 组织记忆，归属组织: id={organization_id}, name={organization_name}")

                logger.info(f"[MemoryWrite] 节点 {node_id} 触发异步写入任务")
                process_memory_write.delay(
                    memory_space_id=memory_space_id,
                    title=title or f"自动记忆-{node_id}",
                    content=message,
                    owner_username=owner_username,
                    owner_domain=owner_domain,
                    organization_id=organization_id,
                )
                logger.info(f"[MemoryWrite] 节点 {node_id} 异步任务已提交")
            except MemorySpace.DoesNotExist:
                logger.error(f"[MemoryWrite] 节点 {node_id} 记忆空间不存在: memory_space_id={memory_space_id}")
            except Exception as e:
                logger.error(f"[MemoryWrite] 节点 {node_id} 触发写入任务失败: {e}", exc_info=True)
        else:
            logger.warning(f"[MemoryWrite] 节点 {node_id} 跳过写入: memory_space_id={memory_space_id}, message_empty={not message}")

        # 透传输入，不影响主流程
        logger.info(f"[MemoryWrite] 节点 {node_id} 执行完成，透传输出: {output_key}")
        return {output_key: message}
