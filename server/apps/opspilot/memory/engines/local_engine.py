"""Local Memory Engine - Uses PostgreSQL database for memory storage."""

import logging
from typing import Any, Dict, List, Optional

from apps.opspilot.memory.engines.base import BaseMemoryEngine, MemoryEntity, MemoryReadResult, MemoryWriteResult

logger = logging.getLogger(__name__)


class LocalMemoryEngine(BaseMemoryEngine):
    """本地记忆引擎

    使用 PostgreSQL 数据库存储记忆，复用现有的 Memory 模型。
    """

    def read(
        self,
        entity: MemoryEntity,
        query: Optional[str] = None,
        top_k: int = 5,
    ) -> MemoryReadResult:
        """读取记忆

        本地引擎不支持语义搜索，按更新时间倒序返回最近的记忆。
        """
        from apps.opspilot.models import Memory

        try:
            # 构建过滤条件
            filters = {"memory_space_id": self.memory_space_id}

            if entity.organization_id is not None:
                # 组织记忆
                filters["organization_id"] = entity.organization_id
            elif entity.user_id:
                # 个人记忆
                if "@" in entity.user_id:
                    username, domain = entity.user_id.rsplit("@", 1)
                else:
                    username = entity.user_id
                    domain = ""
                filters["owner_username"] = username
                filters["owner_domain"] = domain
                filters["organization_id__isnull"] = True

            memories = Memory.objects.filter(**filters).order_by("-updated_at")[:top_k]

            # 构建上下文字符串
            context_parts = []
            raw_memories = []
            for mem in memories:
                context_parts.append(mem.content)
                raw_memories.append(
                    {
                        "id": str(mem.id),
                        "title": mem.title,
                        "content": mem.content,
                        "updated_at": mem.updated_at.isoformat() if mem.updated_at else None,
                    }
                )

            context = "\n\n---\n\n".join(context_parts)
            logger.info(f"[LocalMemoryEngine] Read {len(raw_memories)} memories for space={self.memory_space_id}")

            return MemoryReadResult(
                context=context,
                raw_memories=raw_memories,
                source="local",
            )
        except Exception as e:
            logger.error(f"[LocalMemoryEngine] Read failed: {e}", exc_info=True)
            return MemoryReadResult(context="", raw_memories=[], source="local")

    def write(
        self,
        entity: MemoryEntity,
        content: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        model_id: Optional[int] = None,
    ) -> MemoryWriteResult:
        """写入记忆

        调用现有的 Celery 任务进行异步写入，支持 LLM 智能合并。

        Args:
            model_id: 可选的模型 ID，用于覆盖记忆空间的默认模型
        """
        from apps.opspilot.tasks import process_memory_write, process_memory_write_cache

        try:
            # 解析实体信息
            if entity.organization_id is not None:
                # 组织记忆
                owner_username = f"组织-{entity.organization_id}"
                owner_domain = ""
                organization_id = entity.organization_id

                # 尝试获取组织名称
                try:
                    from apps.system_mgmt.models import Group

                    group = Group.objects.get(id=entity.organization_id)
                    owner_username = group.name
                except Exception:
                    pass
            else:
                # 个人记忆
                if entity.user_id and "@" in entity.user_id:
                    owner_username, owner_domain = entity.user_id.rsplit("@", 1)
                else:
                    owner_username = entity.user_id or "system"
                    owner_domain = ""
                organization_id = None

            workflow_id = metadata.get("workflow_id") if isinstance(metadata, dict) else None
            node_id = metadata.get("node_id") if isinstance(metadata, dict) else None
            write_batch_size = metadata.get("write_batch_size") if isinstance(metadata, dict) else None

            if workflow_id and node_id:
                process_memory_write_cache.delay(
                    memory_space_id=self.memory_space_id,
                    title=title or "自动记忆",
                    content=content,
                    owner_username=owner_username,
                    owner_domain=owner_domain,
                    organization_id=organization_id,
                    model_id=model_id,
                    workflow_id=workflow_id,
                    node_id=node_id,
                    write_batch_size=write_batch_size,
                )
            else:
                process_memory_write.delay(
                    memory_space_id=self.memory_space_id,
                    title=title or "自动记忆",
                    content=content,
                    owner_username=owner_username,
                    owner_domain=owner_domain,
                    organization_id=organization_id,
                    model_id=model_id,
                )
            return MemoryWriteResult(
                success=True,
                message="记忆写入任务已提交",
            )
        except Exception as e:
            logger.error(f"[LocalMemoryEngine] Write failed: {e}", exc_info=True)
            return MemoryWriteResult(
                success=False,
                message=str(e),
            )

    def delete(
        self,
        entity: MemoryEntity,
        memory_id: Optional[str] = None,
    ) -> bool:
        """删除记忆"""
        from apps.opspilot.models import Memory

        try:
            if memory_id:
                # 删除指定记忆
                deleted, _ = Memory.objects.filter(
                    id=int(memory_id),
                    memory_space_id=self.memory_space_id,
                ).delete()
                return deleted > 0
            else:
                # 删除实体的所有记忆
                filters = {"memory_space_id": self.memory_space_id}

                if entity.organization_id is not None:
                    filters["organization_id"] = entity.organization_id
                elif entity.user_id:
                    if "@" in entity.user_id:
                        username, domain = entity.user_id.rsplit("@", 1)
                    else:
                        username = entity.user_id
                        domain = ""
                    filters["owner_username"] = username
                    filters["owner_domain"] = domain
                    filters["organization_id__isnull"] = True

                deleted, _ = Memory.objects.filter(**filters).delete()
                logger.info(f"[LocalMemoryEngine] Deleted {deleted} memories for space={self.memory_space_id}")
                return deleted > 0
        except Exception as e:
            logger.error(f"[LocalMemoryEngine] Delete failed: {e}", exc_info=True)
            return False

    def test_connection(self) -> Dict[str, Any]:
        """本地存储无需测试连接"""
        return {"success": True, "message": "本地存储无需测试"}

    @classmethod
    def get_engine_info(cls) -> Dict[str, str]:
        """获取引擎信息"""
        return {
            "type": "local",
            "name": "本地存储",
            "description": "使用 PostgreSQL 数据库存储记忆",
        }

    @classmethod
    def get_config_schema(cls) -> List[Dict[str, Any]]:
        """本地存储无需额外配置"""
        return []
