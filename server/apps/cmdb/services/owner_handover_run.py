from datetime import timedelta

from django.db.models import Count
from django.utils.timezone import now

from apps.cmdb.models.owner_handover import (
    CANCELLED,
    FAILED,
    OUTCOME_FAILED,
    OUTCOME_SKIPPED,
    OUTCOME_SUCCESS,
    PARTIAL_FAILED,
    SUCCEEDED,
    OwnerHandoverFailure,
    OwnerHandoverOutcome,
    OwnerHandoverTask,
)
from apps.cmdb.services.owner_handover_access import OwnerHandoverRejected, as_user_ids, replace_user_ids, user_label
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger

LEASE = timedelta(minutes=5)

REASON_TEXT = {
    "no_permission": "没有该实例的操作权限",
    "permission_check_failed": "权限校验失败",
    "write_failed": "实例写入失败",
    "missing_identity": "实例缺少业务身份",
}


class HandoverRun:
    def _execute(self, task):
        from_person = self.directory.get(task.from_user_id)
        to_person = self.directory.get(task.to_user_id)
        if not from_person or not to_person:
            raise OwnerHandoverRejected("user_not_found", "交接用户已不存在")
        self._require_target(to_person)
        attr_id, attr_name = self._require_field(task.attr_id, task.attr_name)
        selected, _inapplicable = self._select_models(task.model_ids, attr_id, attr_name)
        models_by_id = {model["model_id"]: model for model in selected}
        source = f"{user_label(from_person)} → {user_label(to_person)}"
        rows, _excluded = self._collect(selected, from_person["id"], to_person["id"], include_denied=True, log_id=str(task.pk))
        done = set(OwnerHandoverOutcome.objects.filter(task=task).values_list("inst_uuid", flat=True))
        if callable(getattr(self.writer, "apply_many", None)):
            self._execute_batched(task, rows, models_by_id, from_person, to_person, source, done)
            return
        for row in rows:
            current = OwnerHandoverTask.objects.get(pk=task.pk)
            if current.cancel_requested:
                break
            identity = row["instance"].get("inst_uuid") or f"missing:{row['model_id']}:{row['instance'].get('inst_name')}"
            if identity in done:
                continue
            if row["denied"]:
                reason = "permission_check_failed" if row["instance"].get("_permission_error") else "no_permission"
                self._record(task, row, identity, OUTCOME_FAILED, reason)
                continue
            fresh = self._fresh_instance(row)
            if fresh is None:
                self._record(task, row, identity, OUTCOME_FAILED, "missing_identity")
                continue
            row = {**row, "instance": fresh}
            changes = self._field_changes(fresh, models_by_id[row["model_id"]], from_person["id"], to_person["id"])
            if not fresh.get("inst_uuid"):
                self._record(task, row, identity, OUTCOME_FAILED, "missing_identity")
                continue
            if not changes:
                self._record(task, row, identity, OUTCOME_SKIPPED, "")
                continue
            payload = {change["attr_id"]: change["after_ids"] for change in changes}
            try:
                self.writer.apply(fresh, payload, self.actor.username, source)
            except Exception as exc:
                logger.debug(
                    "owner handover instance failed, handover_id=%s, inst_uuid=%s, failed_stage=%s, error_type=%s",
                    task.pk,
                    row["instance"].get("inst_uuid"),
                    "write",
                    type(exc).__name__,
                )
                message = str(getattr(exc, "message", "") or "")[:200] if isinstance(exc, BaseAppException) else ""
                self._record(task, row, identity, OUTCOME_FAILED, "write_failed", message)
            else:
                self._record(task, row, identity, OUTCOME_SUCCESS, "")
            done.add(identity)
            OwnerHandoverTask.objects.filter(pk=task.pk).update(lease_expires_at=now() + LEASE)
        self._finish(task)

    def _execute_batched(self, task, rows, models_by_id, from_person, to_person, source, done):
        pending = []
        for row in rows:
            identity = row["instance"].get("inst_uuid") or f"missing:{row['model_id']}:{row['instance'].get('inst_name')}"
            if identity in done:
                continue
            if row["denied"]:
                reason = "permission_check_failed" if row["instance"].get("_permission_error") else "no_permission"
                self._record(task, row, identity, OUTCOME_FAILED, reason)
                continue
            pending.append((identity, row))
        fresh_by_uuid = self._load_fresh([row for _identity, row in pending])
        writable = []
        for identity, row in pending:
            if self._cancelled(task):
                break
            fresh = fresh_by_uuid.get(row["instance"].get("inst_uuid"))
            if fresh is None or not fresh.get("inst_uuid"):
                self._record(task, row, identity, OUTCOME_FAILED, "missing_identity")
                continue
            changes = self._field_changes(fresh, models_by_id[row["model_id"]], from_person["id"], to_person["id"])
            if not changes:
                self._record(task, {**row, "instance": fresh}, identity, OUTCOME_SKIPPED, "")
                continue
            writable.append(
                {
                    **row,
                    "instance": fresh,
                    "identity": identity,
                    "payload": {change["attr_id"]: change["after_ids"] for change in changes},
                }
            )
        chunk_size = max(1, int(getattr(self.writer, "batch_size", 200) or 200))
        for start in range(0, len(writable), chunk_size):
            if self._cancelled(task):
                break
            self._write_chunk(task, writable[start : start + chunk_size], source)
        self._finish(task)

    def _write_chunk(self, task, chunk, source):
        if not chunk or self._cancelled(task):
            return
        try:
            self.writer.apply_many(chunk, self.actor.username, source)
        except Exception as exc:
            if len(chunk) > 1:
                middle = len(chunk) // 2
                self._write_chunk(task, chunk[:middle], source)
                self._write_chunk(task, chunk[middle:], source)
                return
            row = chunk[0]
            logger.debug(
                "owner handover instance failed, handover_id=%s, inst_uuid=%s, failed_stage=%s, error_type=%s",
                task.pk,
                row["instance"].get("inst_uuid"),
                "write",
                type(exc).__name__,
            )
            message = str(getattr(exc, "message", "") or "")[:200] if isinstance(exc, BaseAppException) else ""
            self._record(task, row, row["identity"], OUTCOME_FAILED, "write_failed", message)
        else:
            for row in chunk:
                self._record(task, row, row["identity"], OUTCOME_SUCCESS, "")
        OwnerHandoverTask.objects.filter(pk=task.pk).update(lease_expires_at=now() + LEASE)

    def _cancelled(self, task):
        return OwnerHandoverTask.objects.filter(pk=task.pk, cancel_requested=True).exists()

    def _load_fresh(self, rows):
        getter = getattr(self.catalog, "get_instances", None)
        uuids = [row["instance"].get("inst_uuid") for row in rows if row["instance"].get("inst_uuid")]
        if callable(getter):
            return getter(uuids)
        found = {}
        for row in rows:
            fresh = self._fresh_instance(row)
            if fresh and fresh.get("inst_uuid"):
                found[fresh["inst_uuid"]] = fresh
        return found

    def _finish(self, task):
        current = OwnerHandoverTask.objects.get(pk=task.pk)
        counts = {OUTCOME_SUCCESS: 0, OUTCOME_SKIPPED: 0, OUTCOME_FAILED: 0}
        for row in OwnerHandoverOutcome.objects.filter(task=task).values("result").annotate(total=Count("id")):
            counts[row["result"]] = row["total"]
        if current.cancel_requested:
            status = CANCELLED
            message = "已停止后续实例，已成功的不会回滚"
        elif counts[OUTCOME_FAILED] and counts[OUTCOME_SUCCESS]:
            status = PARTIAL_FAILED
            message = ""
        elif counts[OUTCOME_FAILED] and not counts[OUTCOME_SUCCESS]:
            status = FAILED
            message = "交接失败"
        else:
            status = SUCCEEDED
            message = ""
        logger.info(
            "owner handover finished, handover_id=%s, status=%s, success=%s, skipped=%s, failed=%s",
            task.pk,
            status,
            counts[OUTCOME_SUCCESS],
            counts[OUTCOME_SKIPPED],
            counts[OUTCOME_FAILED],
        )
        OwnerHandoverTask.objects.filter(pk=task.pk).update(
            status=status,
            message=message,
            total_count=sum(counts.values()),
            success_count=counts[OUTCOME_SUCCESS],
            skipped_count=counts[OUTCOME_SKIPPED],
            failed_count=counts[OUTCOME_FAILED],
            finished_at=now(),
        )

    def _record(self, task, row, identity, result, reason_code, message=""):
        OwnerHandoverOutcome.objects.get_or_create(task=task, inst_uuid=identity, defaults={"result": result})
        if result != OUTCOME_FAILED:
            return
        OwnerHandoverFailure.objects.create(
            task=task,
            model_id=row["model_id"],
            model_name=row["model_name"],
            inst_uuid=row["instance"].get("inst_uuid") or "",
            inst_name=row["instance"].get("inst_name") or "",
            reason_code=reason_code,
            message=message or REASON_TEXT.get(reason_code, "交接失败"),
        )

    def _fresh_instance(self, row):
        getter = getattr(self.catalog, "get_instance", None)
        inst_uuid = row["instance"].get("inst_uuid")
        if getter and inst_uuid:
            return getter(row["model_id"], inst_uuid)
        return row["instance"]

    def _collect(self, models, from_user_id, to_user_id, include_denied=False, log_id="preview"):
        executable = []
        denied_rows = []
        excluded = 0
        seen = set()
        for model in models:
            field_ids = [field["attr_id"] for field in model["fields"]]
            instances = self.catalog.find_instances(model["model_id"], from_user_id, field_ids)
            for instance in instances:
                identity = instance.get("inst_uuid") or id(instance)
                if identity in seen:
                    continue
                seen.add(identity)
                changes = self._field_changes(instance, model, from_user_id, to_user_id)
                if not changes:
                    continue
                try:
                    allowed = self.allows(instance)
                except Exception as exc:
                    if not self._permission_logged:
                        self._permission_logged = True
                        logger.exception(
                            "owner handover permission check failed, handover_id=%s, failed_stage=%s, error_type=%s",
                            log_id,
                            "permission",
                            type(exc).__name__,
                        )
                    allowed = False
                    instance = {**instance, "_permission_error": True}
                row = {
                    "model_id": model["model_id"],
                    "model_name": model["model_name"],
                    "instance": instance,
                    "changes": changes,
                    "denied": not allowed,
                }
                if not allowed:
                    excluded += 1
                    if instance.get("_permission_error"):
                        denied_rows.append(row)
                    continue
                executable.append(row)
        executable.sort(key=lambda item: (item["model_name"], item["instance"].get("inst_name") or "", item["instance"].get("inst_uuid") or ""))
        if include_denied:
            return executable + denied_rows, excluded
        return executable, excluded

    def _field_changes(self, instance, model, from_user_id, to_user_id):
        changes = []
        for field in model["fields"]:
            replaced = replace_user_ids(instance.get(field["attr_id"]), from_user_id, to_user_id)
            if replaced is None:
                continue
            changes.append(
                {
                    "attr_id": field["attr_id"],
                    "attr_name": field["attr_name"],
                    "before_ids": as_user_ids(instance.get(field["attr_id"])),
                    "after_ids": replaced,
                }
            )
        return changes
