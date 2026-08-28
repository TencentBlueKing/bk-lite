from celery import shared_task

from apps.core.logger import opspilot_logger as logger

from apps.opspilot.tasks._common import _get_bot_chat_flow, _run_channel_message, _run_in_native_thread

@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="apps.opspilot.tasks.process_wechat_message", queue="opspilot_channel")
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


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="apps.opspilot.tasks.process_enterprise_wechat_aibot_message", queue="opspilot_channel")
def process_enterprise_wechat_aibot_message(self, bot_id, msg_id, message, sender_id, config):
    """处理企微智能机器人短连接消息的 Celery 任务。"""
    from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils

    def _execute():
        handler = EnterpriseWechatAibotChatFlowUtils(bot_id)
        try:
            bot_chat_flow = _get_bot_chat_flow(bot_id)
            if not bot_chat_flow:
                logger.error(f"企微智能机器人消息处理失败：Bot {bot_id} 不存在或未配置 ChatFlow")
                handler.mark_message_failed(msg_id)
                return

            node_id = config["node_id"]
            reply_text = handler.execute_chatflow_with_message(bot_chat_flow, node_id, message, sender_id)
            process_enterprise_wechat_aibot_reply.delay(bot_id, msg_id, config.get("response_url") or "", reply_text)

            logger.info(f"企微智能机器人消息已提交回复任务: bot_id={bot_id}, msg_id={msg_id}")

        except Exception as e:
            logger.exception(f"企微智能机器人消息处理失败: bot_id={bot_id}, msg_id={msg_id}, error={str(e)}")
            handler.mark_message_failed(msg_id)
            raise

    try:
        return _run_in_native_thread(_execute)
    except Exception as e:
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="apps.opspilot.tasks.process_enterprise_wechat_aibot_reply", queue="opspilot_channel")
def process_enterprise_wechat_aibot_reply(self, bot_id, msg_id, response_url, content):
    """异步发送企微智能机器人回复，发送成功后再标记消息完成。"""
    from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils

    handler = EnterpriseWechatAibotChatFlowUtils(bot_id)
    try:
        EnterpriseWechatAibotChatFlowUtils.send_markdown_reply(response_url, content)
        handler.mark_message_completed(msg_id)
    except Exception as e:
        logger.exception(f"企微智能机器人回复发送失败: bot_id={bot_id}, msg_id={msg_id}, error={str(e)}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="apps.opspilot.tasks.process_dingtalk_message", queue="opspilot_channel")
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


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="apps.opspilot.tasks.process_wechat_official_message", queue="opspilot_channel")
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


@shared_task(bind=True, max_retries=2, default_retry_delay=30, name="apps.opspilot.tasks.process_skill_channel_im_message", queue="opspilot_channel")
def process_skill_channel_im_message(self, channel_id, channel_type, method, query, body, headers):
    """智能体 IM 渠道异步处理占位（历史兼容）。四类 IM 已走专用任务。"""
    from apps.opspilot.models import SkillChannel

    channel = SkillChannel.objects.filter(id=channel_id, channel_type=channel_type, enabled=True).first()
    if not channel:
        logger.info("skill IM 跳过：渠道不存在或已下线 channel_id=%s type=%s", channel_id, channel_type)
        return {"skipped": True}
    logger.info(
        "skill IM 消息已受理 channel_id=%s type=%s skill_id=%s body_len=%s",
        channel_id,
        channel_type,
        channel.skill_id,
        len(body or ""),
    )
    return {"accepted": True, "channel_id": channel_id, "skill_id": channel.skill_id}


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="apps.opspilot.tasks.process_skill_channel_aibot_message", queue="opspilot_channel")
def process_skill_channel_aibot_message(self, channel_id, msg_id, message, sender_id, config):
    """智能体企微 aibot：异步单 Agent 执行后投递回覆任务。"""
    from apps.opspilot.models import SkillChannel
    from apps.opspilot.services.skill_channel_aibot import SkillChannelAibotUtils
    from apps.opspilot.services.skill_channel_chat_service import execute_skill_channel_im_sync

    def _execute():
        handler = SkillChannelAibotUtils(channel_id)
        try:
            channel = (
                SkillChannel.objects.filter(
                    id=channel_id,
                    channel_type="enterprise_wechat_aibot",
                    enabled=True,
                )
                .select_related("skill")
                .first()
            )
            if not channel:
                logger.info("skill aibot 跳过：渠道不存在或已下线 channel_id=%s", channel_id)
                handler.mark_message_failed(msg_id)
                return {"skipped": True}

            user_message = ""
            session_id = None
            response_url = (config or {}).get("response_url") or ""
            if isinstance(message, dict):
                user_message = message.get("last_message") or ""
                session_id = message.get("session_id") or None
                response_url = response_url or message.get("response_url") or ""
            else:
                user_message = str(message or "")

            reply_text = execute_skill_channel_im_sync(
                channel=channel,
                user_message=user_message,
                external_user_id=sender_id or "",
                session_id=session_id,
            )
            process_skill_channel_aibot_reply.delay(channel_id, msg_id, response_url, reply_text)
            logger.info("skill aibot 已提交回覆 channel_id=%s msg_id=%s", channel_id, msg_id)
            return {"accepted": True, "channel_id": channel_id, "msg_id": msg_id}
        except Exception:
            logger.exception("skill aibot 消息处理失败 channel_id=%s msg_id=%s", channel_id, msg_id)
            handler.mark_message_failed(msg_id)
            raise

    try:
        return _run_in_native_thread(_execute)
    except Exception as e:
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="apps.opspilot.tasks.process_skill_channel_aibot_reply", queue="opspilot_channel")
def process_skill_channel_aibot_reply(self, channel_id, msg_id, response_url, content):
    """异步发送智能体企微 aibot 回覆，成功后再标记 completed。"""
    from apps.opspilot.services.skill_channel_aibot import SkillChannelAibotUtils

    handler = SkillChannelAibotUtils(channel_id)
    try:
        SkillChannelAibotUtils.send_markdown_reply(response_url, content)
        handler.mark_message_completed(msg_id)
    except Exception as e:
        logger.exception("skill aibot 回覆发送失败 channel_id=%s msg_id=%s", channel_id, msg_id)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="apps.opspilot.tasks.process_skill_channel_wechat_message", queue="opspilot_channel")
def process_skill_channel_wechat_message(self, channel_id, msg_id, message, sender_id, config):
    """智能体企微应用：异步单 Agent 执行并 API 回覆。"""
    from apps.opspilot.models import SkillChannel
    from apps.opspilot.services.skill_channel_chat_service import execute_skill_channel_im_sync
    from apps.opspilot.services.skill_channel_wechat import SkillChannelWechatUtils

    def _execute():
        handler = SkillChannelWechatUtils(channel_id)
        try:
            channel = (
                SkillChannel.objects.filter(
                    id=channel_id,
                    channel_type="enterprise_wechat",
                    enabled=True,
                )
                .select_related("skill")
                .first()
            )
            if not channel:
                logger.info("skill wechat 跳过：渠道不存在或已下线 channel_id=%s", channel_id)
                handler.mark_message_failed(msg_id)
                return {"skipped": True}

            reply_text = execute_skill_channel_im_sync(
                channel=channel,
                user_message=message or "",
                external_user_id=sender_id or "",
                session_id=sender_id or None,
            )
            handler.send_reply(reply_text, sender_id or "", config or {})
            handler.mark_message_completed(msg_id)
            logger.info("skill wechat 处理完成 channel_id=%s msg_id=%s", channel_id, msg_id)
            return {"accepted": True, "channel_id": channel_id, "msg_id": msg_id}
        except Exception:
            logger.exception("skill wechat 消息处理失败 channel_id=%s msg_id=%s", channel_id, msg_id)
            handler.mark_message_failed(msg_id)
            raise

    try:
        return _run_in_native_thread(_execute)
    except Exception as e:
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="apps.opspilot.tasks.process_skill_channel_wechat_official_message", queue="opspilot_channel")
def process_skill_channel_wechat_official_message(self, channel_id, msg_id, message, sender_id, config):
    """智能体微信公众号：异步单 Agent 执行并客服消息回覆。"""
    from apps.opspilot.models import SkillChannel
    from apps.opspilot.services.skill_channel_chat_service import execute_skill_channel_im_sync
    from apps.opspilot.services.skill_channel_wechat_official import SkillChannelWechatOfficialUtils

    def _execute():
        handler = SkillChannelWechatOfficialUtils(channel_id)
        try:
            channel = (
                SkillChannel.objects.filter(
                    id=channel_id,
                    channel_type="wechat_official",
                    enabled=True,
                )
                .select_related("skill")
                .first()
            )
            if not channel:
                logger.info("skill wechat_official 跳过：渠道不存在或已下线 channel_id=%s", channel_id)
                handler.mark_message_failed(msg_id)
                return {"skipped": True}

            reply_text = execute_skill_channel_im_sync(
                channel=channel,
                user_message=message or "",
                external_user_id=sender_id or "",
                session_id=sender_id or None,
            )
            handler.send_reply(reply_text, sender_id or "", config or {})
            handler.mark_message_completed(msg_id)
            logger.info("skill wechat_official 处理完成 channel_id=%s msg_id=%s", channel_id, msg_id)
            return {"accepted": True, "channel_id": channel_id, "msg_id": msg_id}
        except Exception:
            logger.exception("skill wechat_official 消息处理失败 channel_id=%s msg_id=%s", channel_id, msg_id)
            handler.mark_message_failed(msg_id)
            raise

    try:
        return _run_in_native_thread(_execute)
    except Exception as e:
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="apps.opspilot.tasks.process_skill_channel_dingtalk_message", queue="opspilot_channel")
def process_skill_channel_dingtalk_message(self, channel_id, msg_id, text_content, sender_id, webhook_url, config):
    """智能体钉钉 HTTP：异步单 Agent 执行并 webhook markdown 回覆。"""
    from apps.opspilot.models import SkillChannel
    from apps.opspilot.services.skill_channel_chat_service import execute_skill_channel_im_sync
    from apps.opspilot.services.skill_channel_dingtalk import SkillChannelDingtalkUtils

    def _execute():
        handler = SkillChannelDingtalkUtils(channel_id)
        try:
            channel = (
                SkillChannel.objects.filter(
                    id=channel_id,
                    channel_type="dingtalk",
                    enabled=True,
                )
                .select_related("skill")
                .first()
            )
            if not channel:
                logger.info("skill dingtalk 跳过：渠道不存在或已下线 channel_id=%s", channel_id)
                handler.mark_message_failed(msg_id)
                return {"skipped": True}

            reply_text = execute_skill_channel_im_sync(
                channel=channel,
                user_message=text_content or "",
                external_user_id=sender_id or "",
                session_id=sender_id or None,
            )
            if webhook_url and reply_text:
                handler.send_message(webhook_url, "markdown", {"title": "机器人回复", "text": reply_text})
            handler.mark_message_completed(msg_id)
            logger.info("skill dingtalk 处理完成 channel_id=%s msg_id=%s", channel_id, msg_id)
            return {"accepted": True, "channel_id": channel_id, "msg_id": msg_id}
        except Exception:
            logger.exception("skill dingtalk 消息处理失败 channel_id=%s msg_id=%s", channel_id, msg_id)
            handler.mark_message_failed(msg_id)
            raise

    try:
        return _run_in_native_thread(_execute)
    except Exception as e:
        raise self.retry(exc=e)
