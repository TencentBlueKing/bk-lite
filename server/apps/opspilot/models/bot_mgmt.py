import json
import secrets
import uuid

from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_minio_backend import MinioBackend
from django_yaml_field import YAMLField

from apps.core.mixinx import EncryptMixin
from apps.core.models.maintainer_info import MaintainerInfo
from apps.opspilot.enum import BotTypeChoice, ChannelChoices, WorkFlowExecuteType

BOT_CONVERSATION_ROLE_CHOICES = [("user", "用户"), ("bot", "机器人")]


class Bot(MaintainerInfo):
    name = models.CharField(max_length=255, verbose_name="名称")
    introduction = models.TextField(blank=True, null=True, verbose_name="描述")
    team = models.JSONField(default=list)
    channels = models.JSONField(default=list)
    rasa_model = models.ForeignKey("RasaModel", on_delete=models.CASCADE, verbose_name="模型", blank=True, null=True)
    llm_skills = models.ManyToManyField("LLMSkill", verbose_name="LLM技能", blank=True)
    enable_bot_domain = models.BooleanField(verbose_name="启用域名", default=False)
    bot_domain = models.CharField(max_length=255, verbose_name="域名", blank=True, null=True)

    enable_node_port = models.BooleanField(verbose_name="启用端口映射", default=False)
    node_port = models.IntegerField(verbose_name="端口映射", default=5005)
    online = models.BooleanField(verbose_name="是否上线", default=False)
    enable_ssl = models.BooleanField(verbose_name="启用SSL", default=False)
    api_token = models.CharField(max_length=64, default="", blank=True, null=True, verbose_name="API Token")
    replica_count = models.IntegerField(verbose_name="副本数量", default=1)
    bot_type = models.IntegerField(default=BotTypeChoice.PILOT, verbose_name="类型", choices=BotTypeChoice.choices)
    instance_id = models.CharField(max_length=36, blank=True, null=True, verbose_name="实例ID", db_index=True)
    is_builtin = models.BooleanField(default=False, verbose_name="是否内置", db_index=True)
    is_pinned = models.BooleanField(default=False, verbose_name="是否置顶", db_index=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # 如果instance_id为空，自动生成UUID
        if not self.instance_id:
            self.instance_id = str(uuid.uuid4())
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "机器人"
        verbose_name_plural = verbose_name
        db_table = "bot_mgmt_bot"

    @staticmethod
    def get_api_token():
        """
        生成安全的 API Token

        使用 secrets 模块生成密码学安全的随机 token，
        适用于密码、账户认证、安全令牌等场景。

        Returns:
            str: 64 位的十六进制字符串 token
        """
        return secrets.token_hex(32)


class BotChannel(models.Model, EncryptMixin):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, verbose_name="机器人")
    name = models.CharField(max_length=100, verbose_name=_("name"))
    channel_type = models.CharField(max_length=100, choices=ChannelChoices.choices, verbose_name=_("channel type"))
    channel_config = YAMLField(verbose_name=_("channel config"), blank=True, null=True)
    enabled = models.BooleanField(default=False, verbose_name=_("enabled"))

    # 渠道加密字段配置映射（符合开闭原则）
    CHANNEL_ENCRYPT_CONFIG = {
        ChannelChoices.GITLAB: {
            "key": "channels.gitlab_review_channel.GitlabReviewChannel",
            "fields": ["secret_token"],
        },
        ChannelChoices.DING_TALK: {
            "key": "channels.dingtalk_channel.DingTalkChannel",
            "fields": ["client_secret"],
        },
        ChannelChoices.ENTERPRISE_WECHAT: {
            "key": "channels.enterprise_wechat_channel.EnterpriseWechatChannel",
            "fields": ["secret_token", "aes_key", "secret", "token"],
        },
        ChannelChoices.WECHAT_OFFICIAL_ACCOUNT: {
            "key": "channels.wechat_official_account_channel.WechatOfficialAccountChannel",
            "fields": ["aes_key", "secret", "token"],
        },
        ChannelChoices.ENTERPRISE_WECHAT_BOT: {
            "key": "channels.enterprise_wechat_bot_channel.EnterpriseWechatBotChannel",
            "fields": ["secret_token"],
        },
    }

    class Meta:
        db_table = "bot_mgmt_botchannel"

    def _process_channel_encryption(self, encrypt=True):
        """
        处理渠道配置的加密/解密

        Args:
            encrypt: True 表示加密，False 表示解密
        """
        if self.channel_config is None:
            return

        config = self.CHANNEL_ENCRYPT_CONFIG.get(self.channel_type)
        if not config:
            return

        channel_key = config["key"]
        fields = config["fields"]
        channel_data = self.channel_config.get(channel_key)

        if not channel_data:
            return

        process_func = self.encrypt_field if encrypt else self.decrypt_field

        for field in fields:
            process_func(field, channel_data)

    def save(self, *args, **kwargs):
        if self.channel_config is None:
            super().save(*args, **kwargs)
            return

        # 先解密（避免重复加密）
        self._process_channel_encryption(encrypt=False)
        # 再加密
        self._process_channel_encryption(encrypt=True)

        super().save(*args, **kwargs)

    @cached_property
    def decrypted_channel_config(self):
        """获取解密后的渠道配置"""
        if self.channel_config is None:
            return None

        decrypted_config = self.channel_config.copy()
        config = self.CHANNEL_ENCRYPT_CONFIG.get(self.channel_type)

        if not config:
            return decrypted_config

        channel_key = config["key"]
        fields = config["fields"]
        channel_data = decrypted_config.get(channel_key)

        if channel_data:
            for field in fields:
                self.decrypt_field(field, channel_data)

        return decrypted_config

    def format_channel_config(self):
        return_data = {}
        keys = ["secret", "token", "aes_key", "client_secret"]
        for key, value in self.channel_config.items():
            return_data[key] = {i: "******" if v and i in keys else v for i, v in value.items()}
        return return_data


class BotConversationHistory(MaintainerInfo):
    bot = models.ForeignKey("Bot", on_delete=models.CASCADE, verbose_name="机器人")
    conversation_role = models.CharField(max_length=255, verbose_name="对话角色", choices=BOT_CONVERSATION_ROLE_CHOICES)
    conversation = models.TextField(verbose_name="对话内容")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    channel_user = models.ForeignKey("ChannelUser", on_delete=models.CASCADE, verbose_name="通道用户", blank=True, null=True)
    citing_knowledge = models.JSONField(verbose_name="引用知识", default=list, blank=True, null=True)

    def __str__(self):
        return self.conversation

    class Meta:
        verbose_name = "对话历史"
        verbose_name_plural = verbose_name
        db_table = "bot_mgmt_botconversationhistory"


class ConversationTag(models.Model):
    question = models.TextField(verbose_name="问题")
    answer = models.ForeignKey("BotConversationHistory", null=True, blank=True, on_delete=models.CASCADE, verbose_name="回答")
    content = models.TextField(verbose_name="内容")
    knowledge_base_id = models.IntegerField(verbose_name="知识库ID")
    knowledge_document_id = models.IntegerField(verbose_name="知识文档ID")

    class Meta:
        db_table = "bot_mgmt_conversationtag"


class RasaModel(MaintainerInfo):
    name = models.CharField(max_length=255, verbose_name="模型名称")
    description = models.TextField(blank=True, null=True, verbose_name="描述")
    model_file = models.FileField(
        verbose_name="文件",
        null=True,
        blank=True,
        storage=MinioBackend(bucket_name="munchkin-private"),
        upload_to="rasa_models",
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "模型"
        verbose_name_plural = verbose_name
        db_table = "bot_mgmt_rasamodel"


class ChannelUser(models.Model):
    user_id = models.CharField(max_length=100, verbose_name="用户ID")
    name = models.CharField(max_length=100, verbose_name="名称", blank=True, null=True)
    channel_type = models.CharField(max_length=100, choices=ChannelChoices.choices, verbose_name=_("channel type"))

    class Meta:
        verbose_name = "消息通道用户"
        verbose_name_plural = verbose_name
        db_table = "bot_mgmt_channeluser"

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "channel_type": self.channel_type,
            "channel_type_display": self.get_channel_type_display(),
        }


class ChannelGroup(models.Model):
    name = models.CharField(max_length=100)
    group_id = models.CharField(max_length=100)
    channel_type = models.CharField(max_length=100, choices=ChannelChoices.choices, verbose_name=_("channel type"))

    class Meta:
        db_table = "bot_mgmt_channelgroup"


class UserGroup(models.Model):
    user = models.ForeignKey(ChannelUser, on_delete=models.CASCADE)
    group = models.ForeignKey(ChannelGroup, on_delete=models.CASCADE)

    class Meta:
        db_table = "bot_mgmt_usergroup"


class BotWorkFlow(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, verbose_name="机器人")
    flow_json = models.JSONField(verbose_name="流程数据", default=list)
    web_json = models.JSONField(verbose_name="前端数据", default=dict)

    class Meta:
        verbose_name = "机器人工作流"
        verbose_name_plural = verbose_name

    def save(self, *args, **kwargs):
        """保存工作流并自动同步聊天应用"""
        # 先保存工作流
        super().save(*args, **kwargs)

        # 自动同步聊天应用
        try:
            from apps.core.logger import opspilot_logger as logger

            created, updated, deleted = ChatApplication.sync_applications_from_workflow(self)
            logger.info(f"BotWorkFlow {self.id} 保存完成，应用同步结果: " f"创建={created}, 更新={updated}, 删除={deleted}")
        except Exception as e:
            from apps.core.logger import opspilot_logger as logger

            logger.error(f"BotWorkFlow {self.id} 同步聊天应用失败: {str(e)}", exc_info=True)

    @classmethod
    def create_celery_task(cls, bot_id, work_data):
        from django_celery_beat.models import CrontabSchedule, PeriodicTask

        cls.delete_celery_task(bot_id)
        celery_nodes = [i for i in work_data["nodes"] if i.get("type") == "celery"]
        for i in celery_nodes:
            node_id = i["id"]
            data_config = i["data"]["config"]
            hour, minute = data_config.get("time", "00:00").split(":")
            if data_config["frequency"] == "daily":
                crontab_config = {}
            elif data_config["frequency"] == "weekly":
                crontab_config = {"day_of_week": str(data_config.get("weekday", 0))}
            else:
                crontab_config = {
                    "day_of_month": str(data_config.get("day", 1)),
                }
            # 创建或获取 Crontab 调度配置
            crontab_schedule, created = CrontabSchedule.objects.get_or_create(
                minute=minute,
                hour=hour,
                day_of_week=crontab_config.get("day_of_week", "*"),
                day_of_month=crontab_config.get("day_of_month", "*"),
                month_of_year="*",
                timezone=timezone.get_current_timezone(),
            )
            # 准备任务参数
            task_kwargs = {"bot_id": bot_id, "node_id": node_id, "message": data_config["message"]}

            task_name = f"chat_flow_celery_task_{bot_id}_{node_id}"
            # 创建或更新周期性任务
            PeriodicTask.objects.update_or_create(
                name=task_name,
                defaults={
                    "task": "apps.opspilot.tasks.chat_flow_celery_task",
                    "enabled": True,
                    "crontab": crontab_schedule,
                    "kwargs": json.dumps(task_kwargs),  # 使用kwargs而不是args
                    "args": "[]",  # 清空args
                },
            )

    @staticmethod
    def delete_celery_task(bot_id):
        from django_celery_beat.models import PeriodicTask

        task_name = f"chat_flow_celery_task_{bot_id}_"
        PeriodicTask.objects.filter(name__startswith=task_name).delete()


class WorkFlowTaskResult(models.Model):
    bot_work_flow = models.ForeignKey(BotWorkFlow, on_delete=models.CASCADE, verbose_name="机器人工作流")
    run_time = models.DateTimeField(auto_now_add=True, verbose_name="运行时间")
    status = models.CharField(max_length=50, verbose_name="状态")
    input_data = models.TextField(verbose_name="输入数据")
    output_data = models.JSONField(verbose_name="输出数据", default=dict)
    last_output = models.TextField(verbose_name="最后输出", blank=True, null=True)
    execute_type = models.CharField(max_length=50, default="restful")


class WorkFlowConversationHistory(models.Model):
    """
    WorkFlow 对话历史记录表

    记录每次调用 chatflow 的对话详情
    一次完整对话包含两条记录：
    1. 用户输入（conversation_role='user'）
    2. 系统最终输出（conversation_role='bot'）

    注意：定时触发的对话不记录到此表
    """

    bot_id = models.IntegerField(verbose_name="机器人ID", db_index=True)
    node_id = models.CharField(max_length=100, verbose_name="节点ID", default="", db_index=True, help_text="WorkFlow节点入口ID")
    user_id = models.CharField(max_length=100, verbose_name="用户ID", db_index=True)
    conversation_role = models.CharField(
        max_length=10, verbose_name="对话角色", choices=BOT_CONVERSATION_ROLE_CHOICES, db_index=True, help_text="user: 用户输入, bot: 系统最终输出"
    )
    conversation_content = models.TextField(verbose_name="对话内容")
    conversation_time = models.DateTimeField(verbose_name="对话时间", db_index=True)
    entry_type = models.CharField(
        max_length=50,
        verbose_name="入口类型",
        choices=WorkFlowExecuteType.choices,
        default=WorkFlowExecuteType.RESTFUL,
        db_index=True,
        help_text="对话入口类型：openai/restful/enterprise_wechat/wechat_official/dingtalk，celery定时触发不记录",
    )
    session_id = models.CharField(max_length=100, default="")

    class Meta:
        verbose_name = "WorkFlow对话历史"
        verbose_name_plural = "WorkFlow对话历史"
        db_table = "bot_mgmt_workflowconversationhistory"
        ordering = ["-conversation_time"]
        indexes = [
            models.Index(fields=["bot_id", "-conversation_time"]),
            models.Index(fields=["node_id", "-conversation_time"]),
            models.Index(fields=["user_id", "-conversation_time"]),
            models.Index(fields=["entry_type", "-conversation_time"]),
        ]

    def __str__(self):
        return f"{self.get_conversation_role_display()} - {self.conversation_time}"

    @staticmethod
    def display_fields():
        return [
            "id",
            "bot_id",
            "node_id",
            "user_id",
            "conversation_role",
            "conversation_content",
            "conversation_time",
            "entry_type",
        ]


class ChatApplication(models.Model):
    """
    聊天应用模型

    根据 BotWorkFlow 中的入口节点类型自动生成应用配置
    支持的应用类型：mobile（移动端应用）、web_chat（Web对话应用）
    """

    APP_TYPE_MOBILE = "mobile"
    APP_TYPE_WEB_CHAT = "web_chat"

    APP_TYPE_CHOICES = [
        (APP_TYPE_MOBILE, "移动端应用"),
        (APP_TYPE_WEB_CHAT, "Web对话应用"),
    ]

    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, verbose_name="机器人", related_name="chat_applications")
    node_id = models.CharField(max_length=100, verbose_name="节点ID", db_index=True, help_text="入口节点ID")
    app_type = models.CharField(max_length=50, verbose_name="应用类型", choices=APP_TYPE_CHOICES, db_index=True)

    # 通用字段
    app_name = models.CharField(max_length=255, verbose_name="应用名称")
    app_description = models.TextField(verbose_name="应用描述", blank=True, default="")

    # mobile 特有字段
    app_tags = models.JSONField(verbose_name="应用标签", default=list, blank=True, help_text="仅mobile类型使用")

    # web_chat 特有字段
    app_icon = models.CharField(max_length=100, verbose_name="应用图标", blank=True, default="", help_text="仅web_chat类型使用")

    # 节点配置参数（完整存储节点的data.config）
    node_config = models.JSONField(verbose_name="节点配置", default=dict, blank=True, help_text="存储节点的完整配置参数")

    class Meta:
        verbose_name = "聊天应用"
        verbose_name_plural = "聊天应用"
        db_table = "bot_mgmt_chatapplication"
        unique_together = [["bot", "node_id"]]  # 每个Bot的每个节点只能创建一个应用
        ordering = ["id"]
        indexes = [
            models.Index(fields=["bot", "app_type"]),
            models.Index(fields=["node_id"]),
        ]

    def __str__(self):
        return f"{self.app_name} ({self.get_app_type_display()})"

    @classmethod
    def sync_applications_from_workflow(cls, bot_work_flow):
        """
        从工作流同步应用配置

        扫描工作流中的所有节点，查找 mobile 和 web_chat 类型的入口节点，
        自动创建或更新对应的 ChatApplication 记录

        Args:
            bot_work_flow: BotWorkFlow 实例

        Returns:
            tuple: (创建数量, 更新数量, 删除数量)
        """
        from apps.core.logger import opspilot_logger as logger

        bot = bot_work_flow.bot

        # 只有当 Bot 上线时才同步应用
        if not bot.online:
            logger.info(f"Bot {bot.id} 未上线，跳过应用同步")
            # 删除所有相关应用
            deleted_count, _ = cls.objects.filter(bot=bot).delete()
            return 0, 0, deleted_count

        flow_json = bot_work_flow.flow_json
        if not flow_json or not isinstance(flow_json, dict):
            logger.warning(f"BotWorkFlow {bot_work_flow.id} 的 flow_json 为空或格式错误")
            return 0, 0, 0

        nodes = flow_json.get("nodes", [])
        target_node_types = [cls.APP_TYPE_MOBILE, cls.APP_TYPE_WEB_CHAT]

        # 查找所有目标节点
        target_nodes = [node for node in nodes if node.get("type") in target_node_types]

        created_count = 0
        updated_count = 0

        # 记录当前处理的节点ID
        processed_node_ids = set()

        for node in target_nodes:
            node_id = node.get("id")
            node_type = node.get("type")
            node_data = node.get("data", {})
            node_config = node_data.get("config", {})

            if not node_id:
                logger.warning(f"节点缺少ID，跳过: {node}")
                continue

            processed_node_ids.add(node_id)

            # 提取应用参数
            app_params = cls._extract_app_params(node_type, node_config)
            if not app_params:
                logger.warning(f"节点 {node_id} ({node_type}) 缺少必要参数，跳过")
                continue

            # 创建或更新应用
            defaults = {
                "app_type": node_type,
                "app_name": app_params.get("app_name", ""),
                "app_description": app_params.get("app_description", ""),
                "app_tags": app_params.get("app_tags", []),
                "app_icon": app_params.get("app_icon", ""),
                "node_config": node_config,
            }

            app, created = cls.objects.update_or_create(bot=bot, node_id=node_id, defaults=defaults)

            if created:
                created_count += 1
                logger.info(f"创建聊天应用: {app.app_name} (节点: {node_id}, 类型: {node_type})")
            else:
                updated_count += 1
                logger.info(f"更新聊天应用: {app.app_name} (节点: {node_id}, 类型: {node_type})")

        # 删除不再存在的节点对应的应用
        deleted_count, _ = cls.objects.filter(bot=bot).exclude(node_id__in=processed_node_ids).delete()

        if deleted_count > 0:
            logger.info(f"删除 {deleted_count} 个已不存在的节点对应的应用")

        return created_count, updated_count, deleted_count

    @staticmethod
    def _extract_app_params(node_type, node_config):
        """
        从节点配置中提取应用参数

        Args:
            node_type: 节点类型 (mobile/web_chat)
            node_config: 节点配置字典

        Returns:
            dict: 提取的应用参数，如果缺少必要字段则返回None
        """
        if node_type == ChatApplication.APP_TYPE_MOBILE:
            # mobile 需要: appName, appDescription, appTags
            app_name = node_config.get("appName")
            if not app_name:
                return None

            return {
                "app_name": app_name,
                "app_description": node_config.get("appDescription", ""),
                "app_tags": node_config.get("appTags", []),
                "app_icon": "",  # mobile 不使用
            }

        elif node_type == ChatApplication.APP_TYPE_WEB_CHAT:
            # web_chat 需要: appName, appDescription, appIcon
            app_name = node_config.get("appName")
            if not app_name:
                return None

            return {
                "app_name": app_name,
                "app_description": node_config.get("appDescription", ""),
                "app_tags": [],  # web_chat 不使用
                "app_icon": node_config.get("appIcon", ""),
            }

        return None

    def to_dict(self):
        """转换为字典格式，方便API返回"""
        data = {
            "id": self.id,
            "bot_id": self.bot_id,
            "node_id": self.node_id,
            "app_type": self.app_type,
            "app_type_display": self.get_app_type_display(),
            "app_name": self.app_name,
            "app_description": self.app_description,
        }

        # 根据类型添加特定字段
        if self.app_type == self.APP_TYPE_MOBILE:
            data["app_tags"] = self.app_tags
        elif self.app_type == self.APP_TYPE_WEB_CHAT:
            data["app_icon"] = self.app_icon

        return data
