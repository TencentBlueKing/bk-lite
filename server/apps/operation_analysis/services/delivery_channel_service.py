from __future__ import annotations

from dataclasses import dataclass

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
)
from apps.system_mgmt.models import Channel, User as SystemUser


class DashboardReportChannelError(RuntimeError):
    def __init__(self, message: str, *, error_code: str):
        self.error_code = error_code
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedEmailChannel:
    channel_id: int
    config: dict


class DashboardReportDeliveryChannelService:
    """operation_analysis 与 system_mgmt Channel/User 的运行时边界。"""

    @classmethod
    def resolve(
        cls,
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
    ) -> ResolvedEmailChannel:
        if snapshot.email_channel_id is None:
            raise DashboardReportChannelError(
                "邮件通道未配置", error_code="channel_missing"
            )
        channel = Channel.objects.filter(id=snapshot.email_channel_id).first()
        if channel is None:
            raise DashboardReportChannelError(
                "邮件通道不存在", error_code="channel_missing"
            )
        if channel.channel_type != "email":
            raise DashboardReportChannelError(
                "邮件通道不存在或类型不是 email",
                error_code="channel_not_email",
            )

        team_id = snapshot.execution_team_id
        if team_id is None or team_id not in (channel.team or []):
            raise DashboardReportChannelError(
                "邮件通道已不属于本执行组织",
                error_code="channel_team_denied",
            )
        creator = SystemUser.objects.filter(
            username=execution.creator,
            domain=execution.creator_domain,
            disabled=False,
        ).first()
        if team_id not in cls._team_ids(creator):
            raise DashboardReportChannelError(
                "创建者已无权使用本执行组织的邮件通道",
                error_code="channel_team_denied",
            )

        config = dict(channel.config or {})
        cls._validate_config(config)
        encrypted_password = config["smtp_pwd"]
        Channel.decrypt_field("smtp_pwd", config)
        if (
            encrypted_password.startswith("gAAAA")
            and config["smtp_pwd"] == encrypted_password
        ):
            raise DashboardReportChannelError(
                "邮件通道凭据无效",
                error_code="channel_config_invalid",
            )
        return ResolvedEmailChannel(channel_id=channel.id, config=config)

    @staticmethod
    def _team_ids(creator) -> set[int]:
        result = set()
        for item in (getattr(creator, "group_list", None) or []):
            raw_id = item.get("id") if isinstance(item, dict) else item
            try:
                result.add(int(raw_id))
            except (TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _validate_config(config: dict) -> None:
        string_fields = (
            "smtp_server",
            "smtp_user",
            "smtp_pwd",
            "mail_sender",
        )
        if any(
            not isinstance(config.get(field), str)
            or not config[field].strip()
            for field in string_fields
        ):
            raise DashboardReportChannelError(
                "邮件通道配置不完整",
                error_code="channel_config_invalid",
            )
        try:
            port = int(config["port"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DashboardReportChannelError(
                "邮件通道端口配置无效",
                error_code="channel_config_invalid",
            ) from exc
        if not 1 <= port <= 65535:
            raise DashboardReportChannelError(
                "邮件通道端口配置无效",
                error_code="channel_config_invalid",
            )
        config["port"] = port
