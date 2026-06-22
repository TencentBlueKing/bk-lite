from django.utils import timezone

from apps.cmdb.services.collect_hit_state_service import CollectHitStateService
from apps.core.logger import cmdb_logger as logger


class CollectCredentialResultService:
    @staticmethod
    def process_result(data: dict, parse_datetime=None):
        """处理 Stargazer 单 host 单凭据执行结果并回写 CollectTaskCredentialHit。"""
        task_id = data.get("collect_task_id") or data.get("task_id")
        if not task_id:
            logger.warning("[CollectCredentialResult] 回调缺少 collect_task_id，已忽略")
            return {"result": False, "message": "collect_task_id is required"}

        host = str(data.get("host") or "").strip()
        credential_id = str(data.get("credential_id") or "").strip()
        if not host or not credential_id:
            logger.warning(
                "[CollectCredentialResult] 回调缺少 host 或 credential_id，已忽略 task_id=%s, host=%s, credential_id=%s",
                task_id,
                host,
                credential_id,
            )
            return {"result": False, "message": "host and credential_id are required"}

        object_key = f"host:{host}"
        snapshot = dict(data.get("snapshot") or {})
        snapshot.setdefault("host", host)
        finished_at = parse_datetime(data.get("finished_at")) if parse_datetime else None
        finished_at = finished_at or timezone.now()
        success = bool(data.get("success"))

        if success:
            logger.info(
                "[CollectCredentialResult] 凭据采集成功回写 task_id=%s, object_key=%s, credential_id=%s",
                task_id,
                object_key,
                credential_id,
            )
            CollectHitStateService.mark_success(task_id, object_key, credential_id, snapshot, finished_at)
        else:
            logger.warning(
                "[CollectCredentialResult] 凭据采集失败回写 task_id=%s, object_key=%s, credential_id=%s, "
                "failure_kind=%s, error=%s",
                task_id,
                object_key,
                credential_id,
                data.get("failure_kind") or "task",
                (str(data.get("error_message") or ""))[:500],
            )
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

        if failures:
            logger.warning(
                "[CollectCredentialResult] 批量回写存在失败事件 processed=%s, failed=%s",
                processed,
                len(failures),
            )
        else:
            logger.info("[CollectCredentialResult] 批量回写完成 processed=%s", processed)

        return {
            "result": not failures,
            "processed": processed,
            "failed": len(failures),
            "next_since": data.get("next_since") or "",
            "errors": failures,
        }