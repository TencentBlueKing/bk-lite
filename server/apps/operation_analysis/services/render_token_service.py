from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import timedelta

import jwt
from django.db import transaction
from django.utils import timezone

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportRenderToken,
)
from apps.system_mgmt.models import User as SystemUser


DEFAULT_RENDER_TOKEN_TTL_SECONDS = 600


class DashboardReportRenderTokenError(RuntimeError):
    safe_message = "Render Token 无效或已失效"


@dataclass(frozen=True)
class IssuedRenderToken:
    plaintext: str
    expires_at: object


class DashboardReportRenderTokenService:
    @staticmethod
    def _hash(plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    @staticmethod
    def _ttl_seconds() -> int:
        raw_value = os.getenv(
            "DASHBOARD_REPORT_RENDER_TOKEN_TTL_SECONDS",
            str(DEFAULT_RENDER_TOKEN_TTL_SECONDS),
        )
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise DashboardReportRenderTokenError(
                "Render Token TTL 配置无效"
            ) from exc
        if value <= 0:
            raise DashboardReportRenderTokenError(
                "Render Token TTL 配置无效"
            )
        return value

    @classmethod
    @transaction.atomic
    def issue(
        cls,
        execution: DashboardReportExecution,
    ) -> IssuedRenderToken:
        if execution.status != DashboardReportExecution.Status.RUNNING:
            raise DashboardReportRenderTokenError(
                "仅 running Execution 可签发 Render Token"
            )
        if not hasattr(execution, "render_snapshot"):
            raise DashboardReportRenderTokenError("Render Snapshot 不存在")

        plaintext = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(
            seconds=cls._ttl_seconds()
        )
        DashboardReportRenderToken.objects.update_or_create(
            execution=execution,
            defaults={
                "token_hash": cls._hash(plaintext),
                "expires_at": expires_at,
                "consumed_at": None,
            },
        )
        return IssuedRenderToken(
            plaintext=plaintext,
            expires_at=expires_at,
        )

    @classmethod
    @transaction.atomic
    def consume(cls, *, execution_id: int, plaintext: str) -> dict:
        token_hash = cls._hash(plaintext)
        record = (
            DashboardReportRenderToken.objects.select_for_update()
            .select_related("execution")
            .filter(
                execution_id=execution_id,
                token_hash=token_hash,
            )
            .first()
        )
        now = timezone.now()
        if (
            record is None
            or record.consumed_at is not None
            or record.expires_at <= now
        ):
            raise DashboardReportRenderTokenError

        execution = record.execution
        if execution.status != DashboardReportExecution.Status.RUNNING:
            raise DashboardReportRenderTokenError
        try:
            user = SystemUser.objects.get(
                username=execution.creator,
                disabled=False,
            )
        except (
            SystemUser.DoesNotExist,
            SystemUser.MultipleObjectsReturned,
        ) as exc:
            raise DashboardReportRenderTokenError from exc

        secret_key = os.getenv("SECRET_KEY")
        if not secret_key:
            raise DashboardReportRenderTokenError(
                "无法建立 Render 会话"
            )
        record.consumed_at = now
        record.save(update_fields=["consumed_at"])
        session_token = jwt.encode(
            {
                "user_id": user.id,
                "login_time": int(now.timestamp()),
                "jti": secrets.token_hex(16),
                "exp": int(record.expires_at.timestamp()),
                "render_execution_id": execution.id,
            },
            secret_key,
            algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        )
        return {
            "token": session_token,
            "username": user.username,
            "display_name": user.display_name,
            "id": user.id,
            "user_id": user.user_id,
            "domain": user.domain,
            "locale": user.locale,
            "timezone": user.timezone,
            "temporary_pwd": user.temporary_pwd,
            "enable_otp": False,
            "qrcode": False,
        }
