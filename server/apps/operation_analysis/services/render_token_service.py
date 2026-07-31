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
    attempt_no: int


class DashboardReportRenderTokenService:
    """Attempt 级生命周期：每次签发新凭据并废止旧凭据。

    MVP 仍用 Execution 一对一当前有效行；表结构可演进，验收看签发/消费/废止语义。
    """

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
        *,
        attempt_no: int | None = None,
    ) -> IssuedRenderToken:
        if execution.status != DashboardReportExecution.Status.RUNNING:
            raise DashboardReportRenderTokenError(
                "仅 running Execution 可签发 Render Token"
            )
        if not hasattr(execution, "render_snapshot"):
            raise DashboardReportRenderTokenError("Render Snapshot 不存在")

        resolved_attempt = (
            attempt_no
            if attempt_no is not None
            else max(1, int(execution.attempt_count or 1))
        )
        plaintext = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(
            seconds=cls._ttl_seconds()
        )
        existing = (
            DashboardReportRenderToken.objects.select_for_update()
            .filter(execution=execution)
            .first()
        )
        now = timezone.now()
        if existing is not None:
            # 新 attempt：旧明文因 hash 变更失效；同 Execution 同时仅一个有效 Token
            existing.token_hash = cls._hash(plaintext)
            existing.expires_at = expires_at
            existing.consumed_at = None
            existing.revoked_at = None
            existing.attempt_no = resolved_attempt
            existing.save(
                update_fields=[
                    "token_hash",
                    "expires_at",
                    "consumed_at",
                    "revoked_at",
                    "attempt_no",
                ]
            )
        else:
            DashboardReportRenderToken.objects.create(
                execution=execution,
                attempt_no=resolved_attempt,
                token_hash=cls._hash(plaintext),
                expires_at=expires_at,
                consumed_at=None,
                revoked_at=None,
            )
        return IssuedRenderToken(
            plaintext=plaintext,
            expires_at=expires_at,
            attempt_no=resolved_attempt,
        )

    @classmethod
    @transaction.atomic
    def revoke_current(
        cls,
        execution: DashboardReportExecution,
    ) -> bool:
        """显式废止当前 Token（不签发新凭据）。"""
        now = timezone.now()
        updated = (
            DashboardReportRenderToken.objects.filter(
                execution=execution,
                revoked_at__isnull=True,
            ).update(revoked_at=now)
        )
        return updated == 1

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
            or record.revoked_at is not None
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
                "render_attempt_no": record.attempt_no,
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
