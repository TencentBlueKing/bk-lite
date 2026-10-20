from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from apps.rum.services.alert_runtime import RumAlertRuntime
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.alert_store import MemoryEventStore, MemoryPolicyStore
from apps.rum.services.settings import load_rum_settings

DEFAULT_EVAL_WINDOW = timedelta(minutes=15)


class AlertEvaluator:
    """兼容入口：按策略判定，通知只写入投递箱。"""

    def __init__(
        self,
        *,
        policies=None,
        events=None,
        analytics: Analytics | None = None,
        notifier=None,
        now: Callable[[], datetime] | None = None,
        window: timedelta = DEFAULT_EVAL_WINDOW,
        dispatcher=None,
    ):
        del notifier, window
        settings = load_rum_settings()
        self.runtime = RumAlertRuntime(
            policies=policies or MemoryPolicyStore(),
            alerts=events or MemoryEventStore(),
            analytics=analytics or get_analytics(),
            dispatcher=dispatcher,
            now=now,
            tenant_id=settings.tenant_id,
        )

    def evaluate_all(self) -> dict:
        return self.runtime.evaluate_all()

    def evaluate_policy(self, policy_id: str, evaluated_at: datetime) -> str:
        return self.runtime.evaluate_policy(policy_id, evaluated_at)
