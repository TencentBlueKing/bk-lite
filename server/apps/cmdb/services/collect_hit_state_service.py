from datetime import timedelta

from django.db import transaction

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.collect_task_credential_hit import CollectTaskCredentialHit


class CollectHitStateService:
    """负责查询、冷却判断、成功/失败回写。"""

    @staticmethod
    def list_states(task_id):
        states = CollectTaskCredentialHit.objects.filter(task_id=task_id)
        return {(state.object_key, state.credential_id): state for state in states}

    @staticmethod
    def cooldown_hours_for(level):
        if level <= 1:
            return 1
        if level == 2:
            return 4
        return 24

    @staticmethod
    def is_retryable(state, now):
        if state.status != CollectTaskCredentialHit.STATUS_KNOWN_FAILED:
            return True
        if state.next_retry_at is None:
            return True
        return now >= state.next_retry_at

    @staticmethod
    def mark_success(
        task_id,
        object_key,
        credential_id,
        snapshot,
        now,
        event_id="",
        result_id="",
        event_index=-1,
    ):
        with transaction.atomic():
            # 同一任务的凭据状态共享“唯一成功凭据”不变量，
            # 锁住父任务以串行化不同凭据行的并发切换。
            CollectModels.objects.select_for_update().only("id").get(pk=task_id)
            if not CollectHitStateService._accept_success_switch(
                task_id,
                object_key,
                credential_id,
                event_id,
                now,
                result_id,
                event_index,
            ):
                return False
            state, _ = CollectTaskCredentialHit.objects.select_for_update().get_or_create(
                task_id=task_id,
                object_key=object_key,
                credential_id=credential_id,
            )
            if not CollectHitStateService._accept_event(state, event_id, now, result_id, event_index):
                return False
            state.status = CollectTaskCredentialHit.STATUS_SUCCESS
            state.consecutive_failures = 0
            state.cooldown_level = 0
            state.next_retry_at = None
            state.last_success_at = now
            state.last_error = ""
            state.object_snapshot = snapshot or {}
            state.save()
            CollectTaskCredentialHit.objects.filter(
                task_id=task_id,
                object_key=object_key,
                status=CollectTaskCredentialHit.STATUS_SUCCESS,
            ).exclude(credential_id=credential_id).update(
                status=CollectTaskCredentialHit.STATUS_UNTESTED,
                consecutive_failures=0,
                cooldown_level=0,
                next_retry_at=None,
                last_error="",
            )
        return True

    @staticmethod
    def mark_failure(
        task_id,
        object_key,
        credential_id,
        snapshot,
        failure_kind,
        error_message,
        now,
        event_id="",
        result_id="",
        event_index=-1,
    ):
        with transaction.atomic():
            CollectModels.objects.select_for_update().only("id").get(pk=task_id)
            state, _ = CollectTaskCredentialHit.objects.select_for_update().get_or_create(
                task_id=task_id,
                object_key=object_key,
                credential_id=credential_id,
            )
            if not CollectHitStateService._accept_event(state, event_id, now, result_id, event_index):
                return False
            state.object_snapshot = snapshot or {}
            state.last_failure_at = now
            state.last_error = error_message or ""

            if failure_kind == "credential":
                next_level = state.cooldown_level + 1
                state.status = CollectTaskCredentialHit.STATUS_KNOWN_FAILED
                state.consecutive_failures += 1
                state.cooldown_level = next_level
                state.next_retry_at = now + timedelta(hours=CollectHitStateService.cooldown_hours_for(next_level))
            else:
                state.status = CollectTaskCredentialHit.STATUS_UNTESTED
                state.next_retry_at = None

            state.save()
        return True

    @staticmethod
    def _accept_event(state, event_id, event_at, result_id, event_index):
        event_id = str(event_id or "").strip()
        recent_ids = list(state.recent_result_event_ids or [])
        if event_id and event_id in recent_ids:
            return False
        result_id = str(result_id or "").strip()
        try:
            event_index = int(event_index)
        except (TypeError, ValueError):
            event_index = -1
        if state.last_result_at and event_at < state.last_result_at:
            return False
        if state.last_result_at == event_at and result_id and result_id == state.last_result_id and event_index <= state.last_result_event_index:
            return False
        if event_id:
            state.recent_result_event_ids = (recent_ids + [event_id])[-64:]
        state.last_result_at = event_at
        state.last_result_id = result_id
        state.last_result_event_index = event_index
        return True

    @staticmethod
    def _accept_success_switch(
        task_id,
        object_key,
        credential_id,
        event_id,
        event_at,
        result_id,
        event_index,
    ):
        """拒绝较旧成功事件把更新的跨凭据亲和降级。"""
        current = (
            CollectTaskCredentialHit.objects.filter(
                task_id=task_id,
                object_key=object_key,
                status=CollectTaskCredentialHit.STATUS_SUCCESS,
            )
            .exclude(credential_id=credential_id)
            .order_by("-last_result_at", "-id")
            .first()
        )
        if current is None or current.last_result_at is None:
            return True
        if event_at > current.last_result_at:
            return True
        if event_at < current.last_result_at:
            return False
        try:
            normalized_index = int(event_index)
        except (TypeError, ValueError):
            normalized_index = -1
        return bool(result_id) and str(result_id) == current.last_result_id and normalized_index > current.last_result_event_index

    @staticmethod
    def clear_by_credential_ids(task_id, credential_ids):
        if not credential_ids:
            return 0
        deleted_count, _ = CollectTaskCredentialHit.objects.filter(task_id=task_id, credential_id__in=credential_ids).delete()
        return deleted_count
