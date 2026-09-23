from datetime import timedelta
from uuid import UUID

from django.db.models import Q
from django.utils.timezone import now

from apps.cmdb.models.transfer_task import CmdbTransferGuard, CmdbTransferTask
from apps.cmdb.services.transfer_service import TransferService
from apps.core.logger import cmdb_logger as logger


class TransferMaintenance:
    @classmethod
    def dispatch(cls, task_id, send):
        cutoff = now() - timedelta(minutes=1)
        claimed = (
            CmdbTransferTask.objects.filter(pk=task_id, status="queued")
            .filter(Q(dispatched_at__isnull=True) | Q(dispatched_at__lt=cutoff))
            .update(dispatched_at=now())
        )
        if not claimed:
            return
        return cls.publish(task_id, send)

    @staticmethod
    def publish(task_id, send):
        try:
            send(str(task_id))
            return True
        except Exception as exc:
            # 持久化接纳不回滚；下一分钟从数据库补发。
            logger.warning("event=cmdb_transfer_dispatch_deferred task_id=%s failed_stage=dispatch error_type=%s", task_id, type(exc).__name__)
            return False

    @classmethod
    def maintain(cls, send):
        for task in (
            CmdbTransferTask.objects.filter(status="running")
            .filter(Q(lease_expires_at__lte=now()) | Q(deadline_at__lte=now()))
            .only("id", "execution_token")[:500]
        ):
            TransferService.interrupt(task.pk, task.execution_token, "worker_lost")
        can_publish = True
        for task in CmdbTransferTask.objects.filter(status="queued").order_by("created_at")[:500]:
            if task.created_at + timedelta(minutes=30) <= now():
                TransferService.expire_queued(task.pk)
            elif can_publish:
                # Broker 故障时本轮只尝试一次，避免 500 条队列累计连接超时占满默认 Worker。
                can_publish = cls.dispatch(task.pk, send) is not False

    @staticmethod
    def cleanup(files):
        # 文件先删、记录后删，失败保留对象键以便下次补偿。
        tasks = (
            CmdbTransferTask.objects.filter(status__in=TransferService.TERMINAL, holds_slot=False)
            .filter(Q(delete_pending=True) | Q(expires_at__lte=now()))
            .order_by("created_at")
            .iterator(chunk_size=100)
        )
        for task in tasks:
            keys = [task.source_key] + [artifact["key"] for artifact in task.artifacts.values()]
            try:
                for key in filter(None, keys):
                    files.delete(key)
            except Exception as exc:
                logger.warning("event=cmdb_transfer_cleanup_deferred task_id=%s failed_stage=delete_file error_type=%s", task.pk, type(exc).__name__)
                continue
            task.delete()
        # 小批量游标扫描，绝不扫描整个共享桶；未确认退出的执行目录永不作为孤儿删除。
        guard, _ = CmdbTransferGuard.objects.get_or_create(key="orphan_scan")
        previous_cursor = guard.cursor
        scanned = 0
        for item in files.scan(cursor=guard.cursor, limit=1000):
            key = item.object_name
            scanned += 1
            if item.last_modified >= now() - timedelta(days=1):
                guard.cursor = key
                continue
            parts = key.split("/")
            protected = CmdbTransferTask.objects.filter(source_key=key).exists()
            if not protected and len(parts) == 5 and parts[1] != "tmp":
                try:
                    protected = CmdbTransferTask.objects.filter(pk=UUID(parts[2])).exists()
                except (ValueError, TypeError):
                    protected = True  # 不删除未知格式
            if not protected:
                try:
                    files.delete(key)
                except Exception as exc:
                    logger.warning(
                        "event=cmdb_transfer_orphan_cleanup_deferred scan_id=%s failed_stage=delete_file error_type=%s",
                        guard.pk,
                        type(exc).__name__,
                    )
                    break  # 不越过失败对象，次日重试
            guard.cursor = key
        else:
            if scanned < 1000:
                guard.cursor = ""
        CmdbTransferGuard.objects.filter(pk=guard.pk, cursor=previous_cursor).update(cursor=guard.cursor)
