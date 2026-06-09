from datetime import timedelta

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
    def mark_success(task_id, object_key, credential_id, snapshot, now):
        CollectTaskCredentialHit.objects.update_or_create(
            task_id=task_id,
            object_key=object_key,
            credential_id=credential_id,
            defaults={
                "status": CollectTaskCredentialHit.STATUS_SUCCESS,
                "consecutive_failures": 0,
                "cooldown_level": 0,
                "next_retry_at": None,
                "last_success_at": now,
                "last_error": "",
                "object_snapshot": snapshot or {},
            },
        )
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

    @staticmethod
    def mark_failure(task_id, object_key, credential_id, snapshot, failure_kind, error_message, now):
        state, _ = CollectTaskCredentialHit.objects.get_or_create(
            task_id=task_id,
            object_key=object_key,
            credential_id=credential_id,
        )
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

    @staticmethod
    def clear_by_credential_ids(task_id, credential_ids):
        if not credential_ids:
            return 0
        deleted_count, _ = CollectTaskCredentialHit.objects.filter(task_id=task_id, credential_id__in=credential_ids).delete()
        return deleted_count