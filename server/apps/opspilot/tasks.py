import concurrent.futures
import json
import os
import re

from celery import shared_task
from django.core.exceptions import SynchronousOnlyOperation
from django.db import close_old_connections, transaction
from langchain_core.messages import HumanMessage, SystemMessage

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import Bot, BotWorkFlow, LLMModel, Memory, MemorySpace, MemoryWriteCache
from apps.opspilot.services.memory_write_buffer_service import (
    build_batch_content,
    build_memory_target_id,
    extract_memory_write_node_configs,
    normalize_write_batch_size,
    resolve_memory_target,
)
from apps.opspilot.services.workflow_attachment_service import cleanup_expired_workflow_attachments
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine


def _run_in_native_thread(func, *args, **kwargs):
    def _execute(allow_async_unsafe=False):
        close_old_connections()
        previous_async_flag = os.environ.get("DJANGO_ALLOW_ASYNC_UNSAFE")
        if allow_async_unsafe:
            os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

        try:
            return func(*args, **kwargs)
        finally:
            close_old_connections()
            if allow_async_unsafe:
                if previous_async_flag is None:
                    os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
                else:
                    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = previous_async_flag

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(_execute, False)
            return future.result()
        except SynchronousOnlyOperation:
            logger.warning("Fallback with DJANGO_ALLOW_ASYNC_UNSAFE for eventlet ORM task")
            future = executor.submit(_execute, True)
            return future.result()


def _build_memory_write_client(effective_model_id):
    if not effective_model_id:
        return None

    try:
        effective_model_id = int(effective_model_id)
    except (TypeError, ValueError):
        logger.warning(f"[MemoryWriteTask] 模型配置不是有效的 ID: model_id={effective_model_id}，直接处理")
        return None

    try:
        llm_model = LLMModel.objects.get(id=effective_model_id)
    except LLMModel.DoesNotExist:
        logger.warning(f"[MemoryWriteTask] 配置的模型不存在: model_id={effective_model_id}，直接处理")
        return None

    llm_request = BasicLLMRequest(
        openai_api_base=llm_model.openai_api_base,
        openai_api_key=llm_model.openai_api_key,
        model=llm_model.model_name,
        protocol_type=llm_model.protocol_type,
        vendor_type=llm_model.vendor.vendor_type if llm_model.vendor_id else "",
        temperature=0.3,
    )
    return LLMClientFactory.create_client(llm_request, disable_stream=True)


def _summarize_memory_batch_content(memory_space, batch_content: str, model_id=None) -> str:
    effective_model_id = model_id if model_id else memory_space.default_model
    client = _build_memory_write_client(effective_model_id)
    if not client:
        return batch_content

    write_rule = memory_space.write_rule.strip()
    summary_prompt = f"""你是一个记忆批处理助手。请将多条工作流输出整理为一份适合写入记忆的汇总内容。

## 输出要求
- 保留稳定、可复用、对后续对话有价值的信息
- 去除重复、噪音和临时执行细节
- 保持 Markdown 格式
- 只输出最终汇总内容，不要解释过程

## 写入规则
{write_rule or "未配置额外写入规则"}

## 待汇总内容
{batch_content}
"""

    try:
        response = client.invoke(
            [
                SystemMessage(content="你负责将批量工作流输出归纳为一份可写入长期记忆的 Markdown 内容。"),
                HumanMessage(content=summary_prompt),
            ]
        )
        summarized_content = response.content if hasattr(response, "content") else str(response)
        return summarized_content.strip() or batch_content
    except Exception as e:
        logger.error(f"[MemoryWriteBatchTask] 批量归纳失败: {e}，使用原始拼接内容", exc_info=True)
        return batch_content


def _resolve_org_display_name(organization_id) -> str:
    """组织记忆的展示名（owner_username）：优先组名，回退“组织-{id}”。

    与 LocalMemoryEngine.write 的直接写入路径保持一致，避免批量落库时 owner_username 为空，
    导致前端“管理组织”列（读 owner_username）显示空。
    """
    display = f"组织-{organization_id}"
    try:
        from apps.system_mgmt.models import Group

        group = Group.objects.filter(id=organization_id).first()
        if group:
            display = group.name
    except Exception:  # noqa: BLE001
        pass
    return display


def _flush_memory_write_cache_group(
    memory_space_id: int,
    title: str,
    model_id,
    workflow_id: int,
    node_id: str,
    memory_target_id: str,
    batch_size: int = None,
    force_flush: bool = False,
):
    cache_item_ids = []
    normalized_batch_size = normalize_write_batch_size(batch_size)

    with transaction.atomic():
        queryset = (
            MemoryWriteCache.objects.select_for_update()
            .filter(
                workflow_id=workflow_id,
                node_id=node_id,
                memory_target_id=memory_target_id,
                status=MemoryWriteCache.STATUS_PENDING,
            )
            .order_by("created_at", "id")
        )
        ready_items = list(queryset if force_flush else queryset[:normalized_batch_size])
        if not ready_items:
            return False
        if not force_flush and len(ready_items) < normalized_batch_size:
            return False

        cache_item_ids = [item.id for item in ready_items]
        MemoryWriteCache.objects.filter(id__in=cache_item_ids).update(status=MemoryWriteCache.STATUS_PROCESSING)

    try:
        cache_items = list(MemoryWriteCache.objects.filter(id__in=cache_item_ids).order_by("created_at", "id"))
        batch_content = build_batch_content(cache_items)
        if not batch_content:
            MemoryWriteCache.objects.filter(id__in=cache_item_ids).delete()
            return False

        memory_space = MemorySpace.objects.get(id=memory_space_id)
        summarized_content = _summarize_memory_batch_content(memory_space, batch_content, model_id=model_id)
        owner_username, owner_domain, organization_id = resolve_memory_target(memory_space, memory_target_id)
        # 团队记忆 owner_username 为空时补组名，保证前端“管理组织”列有值（与直接写入路径一致）
        if organization_id is not None and not owner_username:
            owner_username = _resolve_org_display_name(organization_id)

        process_memory_write(
            memory_space_id=memory_space_id,
            title=title,
            content=summarized_content,
            owner_username=owner_username,
            owner_domain=owner_domain,
            organization_id=organization_id,
            model_id=model_id,
            skip_write_rule=True,
        )
        MemoryWriteCache.objects.filter(id__in=cache_item_ids).delete()
        return True
    except Exception:
        if cache_item_ids:
            MemoryWriteCache.objects.filter(id__in=cache_item_ids).update(status=MemoryWriteCache.STATUS_PENDING)
        raise


@shared_task
def chat_flow_celery_task(bot_id, node_id, message):
    """ChatFlow周期性任务"""

    def _execute():
        logger.info(f"开始执行ChatFlow周期任务: bot_id={bot_id}, node_id={node_id}")
        bot_obj = Bot.objects.filter(id=bot_id, online=True).first()
        if not bot_obj:
            logger.error(f"Bot {bot_id} 不存在或已下线")
            return
        bot_chat_flow = BotWorkFlow.objects.filter(bot_id=bot_obj.id).first()
        if not bot_chat_flow:
            logger.error(f"Bot {bot_id} 没有配置ChatFlow")
            return
        try:
            engine = create_chat_flow_engine(bot_chat_flow, node_id)
            input_data = {
                "last_message": message,
                "user_id": bot_obj.created_by,
                "bot_id": bot_id,
                "node_id": node_id,
            }
            result = engine.execute(input_data)
            logger.info(f"ChatFlow周期任务执行完成: bot_id={bot_id}, node_id={node_id}, 执行结果为{result}")
        except Exception as e:
            logger.exception(f"ChatFlow周期任务执行失败: bot_id={bot_id}, node_id={node_id}, error={str(e)}")

    return _run_in_native_thread(_execute)


@shared_task
def chat_flow_test_execute_task(workflow_id, node_id, input_data, entry_type, execution_id):
    """ChatFlow测试异步任务"""

    def _execute():
        logger.info(f"开始执行ChatFlow测试异步任务: workflow_id={workflow_id}, node_id={node_id}, execution_id={execution_id}")
        workflow = BotWorkFlow.objects.filter(id=workflow_id).first()
        if not workflow:
            logger.error(f"ChatFlow测试异步任务失败: workflow_id={workflow_id} 不存在")
            return

        try:
            engine = create_chat_flow_engine(workflow, node_id, entry_type=entry_type, execution_id=execution_id)
            if entry_type:
                engine.entry_type = entry_type
            # 来自配置页"测试"的执行，标记 is_test，便于与真实对话执行区分
            engine.is_test = True
            engine.execute(input_data)
            logger.info(f"ChatFlow测试异步任务完成: workflow_id={workflow_id}, node_id={node_id}, execution_id={execution_id}")
        except Exception as e:
            logger.exception(f"ChatFlow测试异步任务失败: workflow_id={workflow_id}, node_id={node_id}, execution_id={execution_id}, error={str(e)}")

    return _run_in_native_thread(_execute)


def _get_bot_chat_flow(bot_id):
    """获取 Bot 的 ChatFlow 配置

    Args:
        bot_id: Bot ID

    Returns:
        BotWorkFlow 对象，如果不存在则返回 None
    """
    bot = Bot.objects.filter(id=bot_id, online=True).first()
    if not bot:
        return None
    return BotWorkFlow.objects.filter(bot_id=bot.id).first()


def _run_channel_message(task, handler_cls, bot_id, msg_id, message, sender_id, config, channel_label):
    """渠道消息处理的共享执行体（async_process_and_reply 风格）

    被企业微信 / 微信公众号等任务复用，差异仅在于 handler 类与日志前缀。

    两阶段去重：调用前已标记为 processing，成功后由 async_process_and_reply 内部
    标记 completed，失败时其内部已调用 mark_message_failed，这里仅负责触发 Celery 重试。

    Args:
        task: 绑定的 Celery 任务实例（用于 task.retry）
        handler_cls: ChatFlow 处理器类
        bot_id: Bot ID
        msg_id: 消息唯一标识
        message: 用户消息内容
        sender_id: 发送者 ID
        config: 渠道配置（包含 node_id 等）
        channel_label: 日志中使用的渠道名称
    """

    def _execute():
        handler = handler_cls(bot_id)
        try:
            bot_chat_flow = _get_bot_chat_flow(bot_id)
            if not bot_chat_flow:
                logger.error(f"{channel_label}消息处理失败：Bot {bot_id} 不存在或未配置 ChatFlow")
                handler.mark_message_failed(msg_id)
                return

            # 执行 ChatFlow 并发送回复
            handler.async_process_and_reply(bot_chat_flow, config, message, sender_id, msg_id)
            logger.info(f"{channel_label}消息处理成功: bot_id={bot_id}, msg_id={msg_id}")

        except Exception as e:
            logger.exception(f"{channel_label}消息处理失败: bot_id={bot_id}, msg_id={msg_id}, error={str(e)}")
            # async_process_and_reply 内部已调用 mark_message_failed
            # 触发 Celery 重试
            raise

    try:
        return _run_in_native_thread(_execute)
    except Exception as e:
        # Celery 重试
        raise task.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_wechat_message(self, bot_id, msg_id, message, sender_id, config):
    """处理企业微信消息的 Celery 任务

    使用两阶段去重：
    - 调用前已标记为 processing
    - 成功后标记为 completed
    - 失败后清除标记并触发重试

    Args:
        bot_id: Bot ID
        msg_id: 消息唯一标识
        message: 用户消息内容
        sender_id: 发送者 ID
        config: 渠道配置（包含 node_id 等）
    """
    from apps.opspilot.utils.wechat_chat_flow_utils import WechatChatFlowUtils

    return _run_channel_message(self, WechatChatFlowUtils, bot_id, msg_id, message, sender_id, config, "微信")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_dingtalk_message(self, bot_id, msg_id, text_content, sender_id, webhook_url, config):
    """处理钉钉消息的 Celery 任务

    使用两阶段去重：
    - 调用前已标记为 processing
    - 成功后标记为 completed
    - 失败后清除标记并触发重试

    Args:
        bot_id: Bot ID
        msg_id: 消息唯一标识
        text_content: 用户消息内容
        sender_id: 发送者 ID
        webhook_url: 钉钉 Webhook URL
        config: 渠道配置（包含 node_id 等）
    """
    from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils

    def _execute():
        handler = DingTalkChatFlowUtils(bot_id)
        try:
            bot_chat_flow = _get_bot_chat_flow(bot_id)
            if not bot_chat_flow:
                logger.error(f"钉钉消息处理失败：Bot {bot_id} 不存在或未配置 ChatFlow")
                handler.mark_message_failed(msg_id)
                return

            # 执行 ChatFlow
            node_id = config.get("node_id")
            reply_text = handler.execute_chatflow_with_message(bot_chat_flow, node_id, text_content, sender_id)

            # 发送回复
            if webhook_url and reply_text:
                markdown_content = {"title": "机器人回复", "text": reply_text}
                handler.send_message(webhook_url, "markdown", markdown_content)

            # 标记完成
            handler.mark_message_completed(msg_id)
            logger.info(f"钉钉消息处理成功: bot_id={bot_id}, msg_id={msg_id}")

        except Exception as e:
            logger.exception(f"钉钉消息处理失败: bot_id={bot_id}, msg_id={msg_id}, error={str(e)}")
            handler.mark_message_failed(msg_id)
            raise

    try:
        return _run_in_native_thread(_execute)
    except Exception as e:
        # Celery 重试
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_wechat_official_message(self, bot_id, msg_id, message, sender_id, config):
    """处理微信公众号消息的 Celery 任务

    使用两阶段去重：
    - 调用前已标记为 processing
    - 成功后标记为 completed
    - 失败后清除标记并触发重试

    Args:
        bot_id: Bot ID
        msg_id: 消息唯一标识
        message: 用户消息内容
        sender_id: 发送者 ID（OpenID）
        config: 渠道配置（包含 node_id, appid, secret 等）
    """
    from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

    return _run_channel_message(self, WechatOfficialChatFlowUtils, bot_id, msg_id, message, sender_id, config, "微信公众号")


@shared_task
def process_memory_write_cache(
    memory_space_id: int,
    title: str,
    content: str,
    owner_username: str,
    owner_domain: str,
    organization_id: int = None,
    model_id: int = None,
    workflow_id: int = None,
    node_id: str = "",
    write_batch_size: int = None,
):
    if not content:
        return

    normalized_batch_size = normalize_write_batch_size(write_batch_size)

    if not workflow_id or not node_id:
        logger.warning("[MemoryWriteBatchTask] 缺少 workflow_id 或 node_id，回退为直接写入")
        process_memory_write(
            memory_space_id=memory_space_id,
            title=title,
            content=content,
            owner_username=owner_username,
            owner_domain=owner_domain,
            organization_id=organization_id,
            model_id=model_id,
        )
        return

    memory_target_id = build_memory_target_id(
        owner_username=owner_username,
        owner_domain=owner_domain,
        organization_id=organization_id,
    )
    workflow_id = int(workflow_id)

    try:
        close_old_connections()

        with transaction.atomic():
            MemoryWriteCache.objects.create(
                workflow_id=workflow_id,
                node_id=node_id,
                memory_target_id=memory_target_id,
                content=content,
            )

            ready_items = list(
                MemoryWriteCache.objects.select_for_update()
                .filter(
                    workflow_id=workflow_id,
                    node_id=node_id,
                    memory_target_id=memory_target_id,
                    status=MemoryWriteCache.STATUS_PENDING,
                )
                .order_by("created_at", "id")[:normalized_batch_size]
            )

            if len(ready_items) < normalized_batch_size:
                logger.info(
                    f"[MemoryWriteBatchTask] 缓存未达到阈值: workflow_id={workflow_id}, "
                    f"node_id={node_id}, target={memory_target_id}, current={len(ready_items)}, "
                    f"required={normalized_batch_size}"
                )
                return

        _flush_memory_write_cache_group(
            memory_space_id=memory_space_id,
            title=title,
            model_id=model_id,
            workflow_id=workflow_id,
            node_id=node_id,
            memory_target_id=memory_target_id,
            batch_size=normalized_batch_size,
        )
    except Exception as e:
        logger.error(
            f"[MemoryWriteBatchTask] 批量写入失败: workflow_id={workflow_id}, node_id={node_id}, target={memory_target_id}, error={e}",
            exc_info=True,
        )
        raise


@shared_task
def flush_memory_write_cache_for_node(
    workflow_id: int,
    node_id: str,
    memory_space_id: int,
    title: str = "",
    model_id: int = None,
):
    close_old_connections()
    target_ids = list(
        MemoryWriteCache.objects.filter(
            workflow_id=workflow_id,
            node_id=node_id,
            status=MemoryWriteCache.STATUS_PENDING,
        )
        .order_by("memory_target_id")
        .values_list("memory_target_id", flat=True)
        .distinct()
    )

    for memory_target_id in target_ids:
        _flush_memory_write_cache_group(
            memory_space_id=memory_space_id,
            title=title or f"自动记忆-{node_id}",
            model_id=model_id,
            workflow_id=int(workflow_id),
            node_id=node_id,
            memory_target_id=memory_target_id,
            force_flush=True,
        )


@shared_task
def flush_all_pending_memory_write_cache():
    close_old_connections()
    pending_pairs = list(MemoryWriteCache.objects.filter(status=MemoryWriteCache.STATUS_PENDING).values("workflow_id", "node_id").distinct())
    if not pending_pairs:
        return

    workflow_ids = {item["workflow_id"] for item in pending_pairs}
    workflow_map = BotWorkFlow.objects.filter(id__in=workflow_ids).in_bulk()
    node_configs_by_workflow = {}

    for pending_pair in pending_pairs:
        workflow_id = pending_pair["workflow_id"]
        workflow = workflow_map.get(workflow_id)
        if not workflow:
            continue

        node_configs = node_configs_by_workflow.setdefault(workflow_id, extract_memory_write_node_configs(workflow.flow_json))
        node_id = pending_pair["node_id"]
        config = node_configs.get(node_id) or {}
        memory_space_id = config.get("memorySpace") or config.get("memory_space_id")
        if not memory_space_id:
            continue
        flush_memory_write_cache_for_node(
            workflow_id=workflow_id,
            node_id=node_id,
            memory_space_id=memory_space_id,
            title=config.get("title", "") or f"自动记忆-{node_id}",
            model_id=config.get("llmModel"),
        )


@shared_task
def process_memory_write(
    memory_space_id: int,
    title: str,
    content: str,
    owner_username: str,
    owner_domain: str,
    organization_id: int = None,
    model_id: int = None,
    skip_write_rule: bool = False,
):
    """异步写入记忆条目，每个用户/组织在每个记忆空间只有一条记忆

    核心逻辑：
    - 个人记忆：按 owner_username + owner_domain + memory_space_id 查找唯一记忆
    - 组织记忆：按 organization_id + memory_space_id 查找唯一记忆
    - 找到则合并内容，未找到则创建新记忆

    Args:
        model_id: 可选，用于覆盖记忆空间的默认模型（workflow 节点级别配置）
        skip_write_rule: 为 True 时跳过 write_rule 规范化，用于批量归纳后的单次写入
    """
    is_org_memory = organization_id is not None
    try:
        close_old_connections()

        # 获取记忆空间配置
        memory_space = MemorySpace.objects.get(id=memory_space_id)
        write_rule = memory_space.write_rule
        # 优先使用传入的 model_id（workflow 节点配置），否则使用记忆空间的默认模型
        effective_model_id = model_id if model_id else memory_space.default_model
        # Step 1: 查找该实体的现有记忆（每个用户/组织只有一条）
        if is_org_memory:
            existing_memory = Memory.objects.filter(
                memory_space_id=memory_space_id,
                organization_id=organization_id,
            ).first()
        else:
            existing_memory = Memory.objects.filter(
                memory_space_id=memory_space_id,
                owner_username=owner_username,
                owner_domain=owner_domain,
                organization_id__isnull=True,
            ).first()

        # 如果没有配置模型，直接创建或追加内容
        if not effective_model_id:
            if existing_memory:
                # 简单追加内容
                existing_memory.content = f"{existing_memory.content}\n\n---\n\n{content}"
                existing_memory.updated_by = owner_username
                existing_memory.save()
            else:
                Memory.objects.create(
                    memory_space_id=memory_space_id,
                    title=title,
                    content=content,
                    owner_username=owner_username,
                    owner_domain=owner_domain,
                    organization_id=organization_id,
                    created_by=owner_username,
                    updated_by=owner_username,
                )
            return

        client = _build_memory_write_client(effective_model_id)
        if not client:
            if existing_memory:
                existing_memory.content = f"{existing_memory.content}\n\n---\n\n{content}"
                existing_memory.updated_by = owner_username
                existing_memory.save()
            else:
                Memory.objects.create(
                    memory_space_id=memory_space_id,
                    title=title,
                    content=content,
                    owner_username=owner_username,
                    owner_domain=owner_domain,
                    organization_id=organization_id,
                    created_by=owner_username,
                    updated_by=owner_username,
                )
            return

        # Step 2: 使用 write_rule 规范化新内容（如果配置了）
        processed_content = content
        if write_rule and not skip_write_rule:
            try:
                messages = [
                    SystemMessage(content=write_rule),
                    HumanMessage(content=content),
                ]
                response = client.invoke(messages)
                processed_content = response.content if hasattr(response, "content") else str(response)
            except Exception as e:
                logger.error(f"[MemoryWriteTask] 规范化失败: {e}，使用原始内容", exc_info=True)

        # Step 3: 如果没有现有记忆，直接创建
        if not existing_memory:
            Memory.objects.create(
                memory_space_id=memory_space_id,
                title=title,
                content=processed_content,
                owner_username=owner_username,
                owner_domain=owner_domain,
                organization_id=organization_id,
                created_by=owner_username,
                updated_by=owner_username,
            )
            return

        # Step 4: 有现有记忆，使用 LLM 智能合并
        merge_prompt = f"""你是一个记忆管理助手。请将新内容与现有记忆智能合并。

## 现有记忆
标题: {existing_memory.title}
内容:
{existing_memory.content}

## 新内容
{processed_content}

## 合并规则（重要！）
你必须将新内容与旧内容**智能合并**，而不是简单替换：
- **保留旧内容中仍然有效的信息**
- **追加新内容中的新信息**
- **如果新旧信息冲突，以新内容为准**（如用户说"我现在喜欢咖啡"覆盖"我喜欢茶"）
- **去除重复信息**，保持内容简洁
- **保持 Markdown 格式**，条目清晰

## 输出格式
请严格按以下 JSON 格式输出，不要输出其他内容：
```json
{{
    "title": "合并后的记忆标题",
    "content": "合并后的完整记忆内容"
}}
```

## 示例
假设现有记忆：
- 标题: 用户饮食偏好
- 内容: "喜欢川菜，不吃香菜"

新内容: "我也喜欢粤式早茶"

正确的合并结果：
```json
{{
    "title": "用户饮食偏好",
    "content": "- 喜欢川菜\\n- 喜欢粤式早茶\\n- 不吃香菜"
}}
```

错误的做法（直接替换）：
```json
{{
    "title": "用户饮食偏好",
    "content": "我也喜欢粤式早茶"
}}
```"""

        try:
            messages = [
                SystemMessage(content="你是一个记忆管理助手，负责智能合并新旧记忆内容。请严格按照 JSON 格式输出。"),
                HumanMessage(content=merge_prompt),
            ]
            response = client.invoke(messages)
            merge_text = response.content if hasattr(response, "content") else str(response)

            # 解析 JSON 响应
            json_match = re.search(r"```json\s*(.*?)\s*```", merge_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = merge_text.strip()
                json_str = re.sub(r"^```\w*\s*", "", json_str)
                json_str = re.sub(r"\s*```$", "", json_str)

            merge_result = json.loads(json_str)
            merged_title = merge_result.get("title", existing_memory.title)
            merged_content = merge_result.get("content", processed_content)

            # 更新现有记忆
            existing_memory.title = merged_title
            existing_memory.content = merged_content
            existing_memory.updated_by = owner_username
            existing_memory.save()

        except json.JSONDecodeError as e:
            logger.error(f"[MemoryWriteTask] JSON 解析失败: {e}，简单追加内容")
            existing_memory.content = f"{existing_memory.content}\n\n---\n\n{processed_content}"
            existing_memory.updated_by = owner_username
            existing_memory.save()
        except Exception as e:
            logger.error(f"[MemoryWriteTask] LLM 合并失败: {e}，简单追加内容", exc_info=True)
            existing_memory.content = f"{existing_memory.content}\n\n---\n\n{processed_content}"
            existing_memory.updated_by = owner_username
            existing_memory.save()

    except MemorySpace.DoesNotExist:
        logger.error(f"[MemoryWriteTask] 记忆空间不存在: space_id={memory_space_id}")
        raise
    except Exception as e:
        logger.error(f"[MemoryWriteTask] 记忆写入失败: {e}", exc_info=True)
        raise


@shared_task
def cleanup_expired_workflow_attachments_task():
    deleted_count = cleanup_expired_workflow_attachments(retention_days=3)
    logger.info("清理过期工作流附件完成: deleted_count=%s", deleted_count)
    return deleted_count


# ---------------------------------------------------------------------------
# Wiki 异步任务(P1):构建 / 资料更新合并 / 全量重建。返回 BuildRecord id;目标不存在返回 None。
# ---------------------------------------------------------------------------


# 说明:以下 wiki 任务短小且对应 service 内部已 @transaction.atomic,故不调用 close_old_connections()
# (该调用会关闭当前连接,与测试事务连接冲突;短任务无需此连接清理)。


@shared_task
def wiki_ingest_material_task(material_id, llm_model_id=None):
    """资料解析(异步):抽取文本 + 生成 AI 摘要。文件/网页解析较重(loader/OCR/LLM),不阻塞前台请求。"""
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.material_service import ingest_material

    material = Material.objects.filter(id=material_id).first()
    if not material:
        logger.error("wiki 解析任务: 资料不存在 id=%s", material_id)
        return None
    return ingest_material(material, llm_model_id=llm_model_id).id


@shared_task
def wiki_build_material_task(material_id, llm_model_id=None, operator=""):
    """从资料构建知识页面(异步)。"""
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.build_service import build_from_material

    material = Material.objects.filter(id=material_id).first()
    if not material:
        logger.error("wiki 构建任务: 资料不存在 id=%s", material_id)
        return None
    return build_from_material(material, llm_model_id=llm_model_id, operator=operator).id


@shared_task
def wiki_propose_update_task(material_id, llm_model_id=None, operator=""):
    """资料更新后的安全合并(异步)。"""
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.update_service import propose_update

    material = Material.objects.filter(id=material_id).first()
    if not material:
        logger.error("wiki 资料更新任务: 资料不存在 id=%s", material_id)
        return None
    return propose_update(material, llm_model_id=llm_model_id, operator=operator).id


@shared_task
def wiki_rebuild_kb_task(kb_id, llm_model_id=None, operator=""):
    """Schema 变更全量重建(异步)。"""
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = WikiKnowledgeBase.objects.filter(id=kb_id).first()
    if not kb:
        logger.error("wiki 重建任务: 知识库不存在 id=%s", kb_id)
        return None
    return rebuild_knowledge_base(kb, llm_model_id=llm_model_id, operator=operator).id


@shared_task
def wiki_refresh_web_materials_task():
    """网页资料定时刷新:重新抓取所有 web 资料并重新摄取,内容变化的触发安全更新。

    供 Celery beat 周期调度。返回 {checked, updated} 统计。
    """
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.material_service import ingest_material
    from apps.opspilot.services.wiki.update_service import propose_update

    web_materials = Material.objects.filter(material_type="web")
    checked = updated = 0
    for material in web_materials:
        checked += 1
        prev_hash = material.content_hash
        material = ingest_material(material, llm_model_id=material.knowledge_base.llm_model_id)
        if material.status == "done" and material.content_hash and material.content_hash != prev_hash:
            updated += 1
            try:
                propose_update(material, llm_model_id=material.knowledge_base.llm_model_id, operator="web_refresh")
            except Exception:
                logger.exception("wiki 网页刷新触发更新失败 material=%s", material.id)
    logger.info("wiki 网页资料刷新完成: checked=%s updated=%s", checked, updated)
    return {"checked": checked, "updated": updated}
