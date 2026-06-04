from django.utils import timezone

from apps.cmdb.services.collect_hit_state_service import CollectHitStateService


class CollectCredentialResultService:
    @staticmethod
    def process_result(data: dict, parse_datetime=None):
        """处理 Stargazer 单 host 单凭据执行结果并回写 CollectTaskCredentialHit。"""
        task_id = data.get("collect_task_id") or data.get("task_id")
        if not task_id:
            return {"result": False, "message": "collect_task_id is required"}

        host = str(data.get("host") or "").strip()
        credential_id = str(data.get("credential_id") or "").strip()
        if not host or not credential_id:
            return {"result": False, "message": "host and credential_id are required"}

        object_key = f"host:{host}"
        snapshot = dict(data.get("snapshot") or {})
        snapshot.setdefault("host", host)
        finished_at = parse_datetime(data.get("finished_at")) if parse_datetime else None
        finished_at = finished_at or timezone.now()
        success = bool(data.get("success"))

        if success:
            CollectHitStateService.mark_success(task_id, object_key, credential_id, snapshot, finished_at)
        else:
            CollectHitStateService.mark_failure(
                task_id,
                object_key,
                credential_id,
                snapshot,
                data.get("failure_kind") or "task",
                data.get("error_message") or "",
                finished_at,
            )

        return {"result": True, "task_id": task_id, "object_key": object_key, "credential_id": credential_id}

    @staticmethod
    def process_batch(data: dict, parse_datetime=None):
        events = data.get("events") if isinstance(data, dict) else None
        if not isinstance(events, list):
            return CollectCredentialResultService.process_result(data or {}, parse_datetime=parse_datetime)

        processed = 0
        failures = []
        for item in events:
            result = CollectCredentialResultService.process_result(item or {}, parse_datetime=parse_datetime)
            if result.get("result"):
                processed += 1
            else:
                failures.append(result)

        return {
            "result": not failures,
            "processed": processed,
            "failed": len(failures),
            "next_since": data.get("next_since") or "",
            "errors": failures,
        }