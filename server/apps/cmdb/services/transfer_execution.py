import json
import threading
from contextlib import contextmanager
from datetime import timedelta
from tempfile import TemporaryFile

import openpyxl
from django.db import close_old_connections
from django.utils.timezone import now

from apps.cmdb.models.transfer_task import CmdbTransferTask
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.transfer_authorization import TransferAuthorization
from apps.cmdb.services.transfer_files import TransferFiles, storage_failure_details
from apps.cmdb.services.transfer_import import TransferImport
from apps.cmdb.services.transfer_service import TransferError, TransferService
from apps.cmdb.services.transfer_validation import inspect_workbook
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info


@contextmanager
def execution_heartbeat(task_id, token):
    stopped = threading.Event()

    def beat():
        while not stopped.wait(20):
            close_old_connections()
            try:
                count = CmdbTransferTask.objects.filter(
                    pk=task_id, execution_token=token, status="running", deadline_at__gt=now(), lease_expires_at__gt=now()
                ).update(lease_expires_at=now() + timedelta(minutes=2))
                if not count:
                    return
            except Exception:
                return  # 数据库不可用时不假装续租成功；主执行/维护按租约失败关闭。
            finally:
                close_old_connections()

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=1)


class TransferExecution:
    @classmethod
    def run(cls, task_id, *, files=None):
        token = TransferService.claim(task_id)
        if not token:
            return
        task = CmdbTransferTask.objects.select_related("owner").get(pk=task_id)
        try:
            files = files or TransferFiles()
            with execution_heartbeat(task.pk, token):
                context = TransferAuthorization.revalidate(task)
                prefix = f"transfer/{task.owner_id}/{task.pk}/{token}"
                if task.kind == "export":
                    summary, artifacts = cls.export(task, token, context, files, prefix)
                else:
                    summary, artifacts = cls.import_file(task, token, context, files, prefix)
                TransferAuthorization.revalidate(task)
                status = "partial_success" if summary.get("failed_rows") or summary.get("failed_relations") else "succeeded"
                if task.kind == "import" and summary.get("failed_rows") and not (summary.get("created") or summary.get("updated")):
                    status = "failed"
                if not TransferService.finish(task.pk, token, status, summary=summary, artifacts=artifacts):
                    TransferService.interrupt(task.pk, token, "publication_lost")
        except TransferError as exc:
            TransferService.fail_execution(task.pk, token, exc.code, str(exc), execution_stopped=True, error_type="TransferError")
        except Exception as exc:
            storage_code, storage_message = storage_failure_details(exc)
            task.refresh_from_db()
            stage = "object_storage" if storage_code else task.summary.get("_failure", {}).get("stage", task.phase)
            logger.error(
                "event=cmdb_transfer_failed task_id=%s failed_stage=%s error_type=%s storage_code=%s",
                str(task.pk),
                stage,
                type(exc).__name__,
                storage_code or "-",
                exc_info=safe_exception_info(exc),
            )
            if isinstance(exc, TimeoutError):
                message = "依赖服务请求超时，请稍后重试"
            elif isinstance(exc, ConnectionError):
                message = "依赖服务连接失败，请检查服务状态"
            else:
                message = "数据处理异常，请根据任务编号联系管理员查看日志"
            TransferService.fail_execution(
                task.pk,
                token,
                "storage_unavailable" if storage_code else "execution_failed",
                storage_message or f"{message}（{type(exc).__name__}）",
                execution_stopped=True,
                error_type=type(exc).__name__,
            )
        finally:
            # 正常回栈就是本执行已停止的确认；不依赖租约过期来假装杀掉线程。
            # 包括 watchdog 已置失败但旧同步调用现在才返回、以及成功结果被拒绝发布。
            TransferService.fail_execution(
                task.pk,
                token,
                "execution_stopped",
                "执行已终止，已写入的数据保留",
                execution_stopped=True,
            )

    @staticmethod
    def export(task, token, context, files, prefix):
        params = task.params
        ids = []
        uuids = params.get("inst_uuids", [])
        if uuids:
            for offset in range(0, len(uuids), 500):
                instances = InstanceManage.query_entity_by_uuids(uuids[offset : offset + 500])
                if len(instances) != len(uuids[offset : offset + 500]):
                    raise TransferError("instance_not_found", "所选实例已删除或不可访问", 404)
                for item in instances:
                    if item["model_id"] != task.model_id:
                        raise TransferError("invalid_scope", "所选实例不属于当前模型")
                    TransferAuthorization.check_instance(context, item)
                    ids.append(item["_id"])
        exported = 0
        with TemporaryFile(mode="w+b") as manifest:

            def progress(count):
                nonlocal exported
                TransferAuthorization.revalidate(task)
                TransferService.progress(task.pk, token, "generating_file", count)
                exported = count

            def inspect_batch(batch, relation_rows):
                ids_by_model = {task.model_id: {item["inst_uuid"] for item in batch}}
                for row in relation_rows:
                    peer_model = row["dst_model_id"] if row["src_model_id"] == task.model_id else row["src_model_id"]
                    ids_by_model.setdefault(peer_model, set()).add(row["peer_uuid"])
                for model_id, identifiers in ids_by_model.items():
                    scope = (
                        context
                        if model_id == task.model_id
                        else TransferAuthorization.resolve(task.owner, task.team_id, task.include_children, model_id, "export")
                    )
                    # 同时保护关联对端；不能导出无权查看的名称，也不能让旧文件绕过资源归属变化。
                    identifiers = sorted(identifiers)
                    for offset in range(0, len(identifiers), 500):
                        selected = identifiers[offset : offset + 500]
                        instances = InstanceManage.query_entity_by_uuids(selected)
                        if len(instances) != len(selected):
                            raise TransferError("scope_changed", "实例在导出期间发生变化，请重新提交")
                        for instance in instances:
                            if instance["model_id"] != model_id:
                                raise TransferError("scope_changed", "实例模型已变化，请重新导出", 403)
                            TransferAuthorization.check_instance(scope, instance)
                        manifest.write(
                            (
                                json.dumps({"model_id": model_id, "ids": selected, "authorization": scope.snapshot, "schema_hash": scope.schema_hash})
                                + "\n"
                            ).encode()
                        )

            with InstanceManage.inst_export(
                task.model_id,
                ids,
                context.permission_map,
                creator=context.actor.username,
                attr_list=params["attr_list"],
                association_list=params.get("association_list", []),
                file_backed=True,
                row_limit=100000,
                progress=progress,
                inspect_batch=inspect_batch,
                byte_limit=files.MAX_BYTES,
            ) as stream:
                TransferService.progress(task.pk, token, "uploading_result", exported, exported)
                output = files.put(f"{prefix}/export.xlsx", stream)
            manifest.seek(0)
            references = files.put(f"{prefix}/manifest.jsonl", manifest)
        return {"exported": exported}, {"result": output, "manifest": references}

    @staticmethod
    def import_file(task, token, context, files, prefix):
        def progress(processed, total, summary, phase):
            TransferService.progress(task.pk, token, phase, processed, total, summary)

        TransferService.progress(task.pk, token, "reading_source")
        with files.local_copy(task.source_key) as stream:
            allowed = {item["attr_id"] for item in context.attrs} | {item["model_asst_id"] for item in context.associations}
            TransferService.progress(task.pk, token, "validating_file")
            inspected = inspect_workbook(stream, task.model_id, allowed_fields=allowed)
            if inspected["sha256"] != task.source_hash:
                raise TransferError("source_changed", "上传源文件校验失败")
            summary, errors = TransferImport.run(task, stream, context, progress)
        TransferService.progress(task.pk, token, "uploading_result", summary=summary)
        artifacts = {}
        if errors:
            book = openpyxl.Workbook(write_only=True)
            sheet = book.create_sheet("errors")
            sheet.append(["Excel 行号", "类型", "失败原因"])
            for row in errors:
                sheet.append(list(row))
            with TemporaryFile(mode="w+b") as report:
                book.save(report)
                report.seek(0)
                artifacts["errors"] = files.put(f"{prefix}/errors.xlsx", report)
            book.close()
        return summary, artifacts

    @staticmethod
    def validate_download(task, files):
        TransferAuthorization.revalidate(task)
        if task.kind != "export":
            return
        with files.local_copy(task.artifacts["manifest"]["key"], max_bytes=100 * 1024 * 1024) as manifest:
            for line in manifest:
                batch = json.loads(line)
                scope = TransferAuthorization.resolve(task.owner, task.team_id, task.include_children, batch["model_id"], "export")
                if batch["authorization"] != scope.snapshot or batch["schema_hash"] != scope.schema_hash:
                    raise TransferError("authorization_changed", "文件授权范围已变化，请重新导出", 403)
                instances = InstanceManage.query_entity_by_uuids(batch["ids"])
                if len(instances) != len(batch["ids"]):
                    raise TransferError("scope_changed", "文件引用的实例已变化，请重新导出", 403)
                for instance in instances:
                    if instance["model_id"] != batch["model_id"]:
                        raise TransferError("scope_changed", "实例模型已变化，请重新导出", 403)
                    TransferAuthorization.check_instance(scope, instance)
