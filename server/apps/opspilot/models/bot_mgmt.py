import binascii
import json
import os

from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_minio_backend import MinioBackend
from django_yaml_field import YAMLField

from apps.core.mixinx import EncryptMixin
from apps.core.models.maintainer_info import MaintainerInfo
from apps.opspilot.enum import BotTypeChoice, ChannelChoices

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

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "机器人"
        verbose_name_plural = verbose_name
        db_table = "bot_mgmt_bot"

    @staticmethod
    def get_api_token():
        return binascii.hexlify(os.urandom(32)).decode()


class BotChannel(models.Model, EncryptMixin):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, verbose_name="机器人")
    name = models.CharField(max_length=100, verbose_name=_("name"))
    channel_type = models.CharField(max_length=100, choices=ChannelChoices.choices, verbose_name=_("channel type"))
    channel_config = YAMLField(verbose_name=_("channel config"), blank=True, null=True)
    enabled = models.BooleanField(default=False, verbose_name=_("enabled"))

    class Meta:
        db_table = "bot_mgmt_botchannel"

    def save(self, *args, **kwargs):
        if self.channel_config is None:
            super(BotChannel, self).save()
        if self.channel_type == ChannelChoices.GITLAB:
            self.decrypt_field("secret_token", self.channel_config["channels.gitlab_review_channel.GitlabReviewChannel"])

            self.encrypt_field("secret_token", self.channel_config["channels.gitlab_review_channel.GitlabReviewChannel"])

        elif self.channel_type == ChannelChoices.DING_TALK:
            self.decrypt_field("client_secret", self.channel_config["channels.dingtalk_channel.DingTalkChannel"])
            self.encrypt_field("client_secret", self.channel_config["channels.dingtalk_channel.DingTalkChannel"])

        elif self.channel_type == ChannelChoices.ENTERPRISE_WECHAT:
            key = "channels.enterprise_wechat_channel.EnterpriseWechatChannel"
            self.decrypt_field("secret_token", self.channel_config[key])
            self.decrypt_field("aes_key", self.channel_config[key])
            self.decrypt_field("secret", self.channel_config[key])
            self.decrypt_field("token", self.channel_config[key])
            self.encrypt_field("secret_token", self.channel_config[key])
            self.encrypt_field("aes_key", self.channel_config[key])
            self.encrypt_field("secret", self.channel_config[key])
            self.encrypt_field("token", self.channel_config[key])
        elif self.channel_type == ChannelChoices.WECHAT_OFFICIAL_ACCOUNT:
            key = "channels.wechat_official_account_channel.WechatOfficialAccountChannel"
            self.decrypt_field("aes_key", self.channel_config[key])
            self.decrypt_field("secret", self.channel_config[key])
            self.decrypt_field("token", self.channel_config[key])
            self.encrypt_field("aes_key", self.channel_config[key])
            self.encrypt_field("secret", self.channel_config[key])
            self.encrypt_field("token", self.channel_config[key])
        elif self.channel_type == ChannelChoices.ENTERPRISE_WECHAT_BOT:
            self.decrypt_field(
                "secret_token",
                self.channel_config["channels.enterprise_wechat_bot_channel.EnterpriseWechatBotChannel"],
            )
            self.encrypt_field(
                "secret_token",
                self.channel_config["channels.enterprise_wechat_bot_channel.EnterpriseWechatBotChannel"],
            )

        super().save(*args, **kwargs)

    @cached_property
    def decrypted_channel_config(self):
        decrypted_config = self.channel_config.copy()
        if self.channel_type == ChannelChoices.GITLAB:
            self.decrypt_field("secret_token", decrypted_config["channels.gitlab_review_channel.GitlabReviewChannel"])

        if self.channel_type == ChannelChoices.DING_TALK:
            self.decrypt_field("client_secret", decrypted_config["channels.dingtalk_channel.DingTalkChannel"])

        elif self.channel_type == ChannelChoices.ENTERPRISE_WECHAT:
            key = "channels.enterprise_wechat_channel.EnterpriseWechatChannel"

            self.decrypt_field("secret_token", decrypted_config[key])
            self.decrypt_field("aes_key", decrypted_config[key])
            self.decrypt_field("secret", decrypted_config[key])
            self.decrypt_field("token", decrypted_config[key])

        elif self.channel_type == ChannelChoices.ENTERPRISE_WECHAT_BOT:
            self.decrypt_field("secret_token", decrypted_config["channels.enterprise_wechat_bot_channel.EnterpriseWechatBotChannel"])
        elif self.channel_type == ChannelChoices.WECHAT_OFFICIAL_ACCOUNT:
            key = "channels.wechat_official_account_channel.WechatOfficialAccountChannel"
            self.decrypt_field("secret", decrypted_config[key])
            self.decrypt_field("token", decrypted_config[key])
            self.decrypt_field("aes_key", decrypted_config[key])

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
