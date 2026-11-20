import hashlib
import json
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.db import connection, transaction
from django.db.models import Q
from django.utils.timezone import now

from apps.cmdb.models.owner_handover import (
    ACTIVE_STATUSES,
    CANCELLED,
    FAILED,
    OUTCOME_FAILED,
    OUTCOME_SUCCESS,
    QUEUED,
    RUNNING,
    TERMINAL_STATUSES,
    OwnerHandoverOutcome,
    OwnerHandoverTask,
)
from apps.cmdb.services.owner_handover_access import (
    OwnerHandoverRejected,
    UserDirectory,
    allows_instance,
    as_user_ids,
    organization_label,
    user_label,
)
from apps.cmdb.services.owner_handover_run import HandoverRun
from apps.core.logger import cmdb_logger as logger
from apps.system_mgmt.models.user import EmploymentStatus

__all__ = [
    "OwnerHandoverRejected",
    "OwnerHandoverService",
    "UserDirectory",
    "allows_instance",
    "as_user_ids",
    "dispatch_owner_handover",
    "execute_saved_task",
]

PREVIEW_SALT = "owner-handover-preview"
PREVIEW_MAX_AGE = 30 * 60
PAGE_SIZE_MAX = 50
CLEANUP_DAYS_MAX = 3650
LEASE = timedelta(minutes=5)


class OwnerHandoverService(HandoverRun):
    def __init__(self, catalog, writer, directory, allows, actor, team_id, include_children, dispatch=None):
        self.catalog = catalog
        self.writer = writer
        self.directory = directory
        self.allows = allows
        self.actor = actor
        self.team_id = int(team_id)
        self.include_children = bool(include_children)
        self.dispatch = dispatch or dispatch_owner_handover
        self._permission_logged = False

    @classmethod
    def for_actor(cls, user, team_id, include_children, dispatch=None):
        from apps.cmdb.services.owner_handover_graph import GraphOwnerCatalog, InstanceHandoverWriter

        directory = UserDirectory(getattr(user, "domain", "domain.com") or "domain.com")
        return cls(
            GraphOwnerCatalog(),
            InstanceHandoverWriter(user, team_id, include_children),
            directory,
            lambda instance: allows_instance(user, team_id, include_children, instance),
            user,
            team_id,
            include_children,
            dispatch=dispatch,
        )

    def list_models(self):
        return self.catalog.list_models()

    def preview(self, from_user_id, to_user_id, model_ids=None, page=1, page_size=20, attr_id="", attr_name=""):
        from_person, to_person = self._require_people(from_user_id, to_user_id)
        attr_id, attr_name = self._require_field(attr_id, attr_name)
        page = self._page(page)
        page_size = self._page_size(page_size)
        selected, inapplicable = self._select_models(model_ids, attr_id, attr_name)
        executable, excluded = self._collect(selected, from_person["id"], to_person["id"])
        start = (page - 1) * page_size
        items = [self._preview_item(row, from_person, to_person) for row in executable[start : start + page_size]]
        token = signing.dumps(
            {
                "operator": self.actor.username,
                "domain": getattr(self.actor, "domain", "domain.com"),
                "from_user_id": from_person["id"],
                "to_user_id": to_person["id"],
                "attr_id": attr_id,
                "attr_name": attr_name,
                "model_ids": [model["model_id"] for model in selected],
                "team_id": self.team_id,
                "include_children": self.include_children,
            },
            salt=PREVIEW_SALT,
        )
        return {
            "preview_token": token,
            "total": len(executable),
            "excluded_no_permission": excluded,
            "inapplicable_models": inapplicable,
            "by_model": self._counts(executable),
            "items": items,
            "page": page,
            "page_size": page_size,
            "from_user": {**from_person, "label": user_label(from_person)},
            "to_user": {**to_person, "label": user_label(to_person)},
            "attr_id": attr_id,
            "attr_name": attr_name,
        }

    def submit(self, preview_token, idempotency_key):
        payload = self._load_token(preview_token)
        from_person, to_person = self._require_people(payload["from_user_id"], payload["to_user_id"])
        attr_id, attr_name = self._require_field(payload.get("attr_id"), payload.get("attr_name"))
        model_ids = list(payload["model_ids"])
        selected, _inapplicable = self._select_models(model_ids, attr_id, attr_name)
        executable, _excluded = self._collect(selected, from_person["id"], to_person["id"])
        if not executable:
            raise OwnerHandoverRejected("no_instances", "没有可交接的实例")
        digest = self._request_hash(from_person["id"], to_person["id"], model_ids, attr_id, attr_name)
        key = str(idempotency_key or "").strip()
        if not key:
            raise OwnerHandoverRejected("idempotency_required", "缺少 Idempotency-Key")
        created = False
        with transaction.atomic():
            active = OwnerHandoverTask.objects.filter(from_user_id=from_person["id"], status__in=ACTIVE_STATUSES)
            if connection.features.has_select_for_update:
                active = active.select_for_update()
            busy = active.exists()
            existing = OwnerHandoverTask.objects.filter(
                operator_username=self.actor.username,
                operator_domain=getattr(self.actor, "domain", "domain.com"),
                idempotency_key=key,
            ).first()
            if existing:
                if existing.request_hash != digest:
                    raise OwnerHandoverRejected("idempotency_conflict", "相同幂等键对应了不同的交接内容", 409)
                task = existing
            else:
                if busy:
                    raise OwnerHandoverRejected("handover_busy", "该原负责人已有进行中的交接", 409)
                task = OwnerHandoverTask.objects.create(
                    operator_username=self.actor.username,
                    operator_domain=getattr(self.actor, "domain", "domain.com") or "domain.com",
                    from_user_id=from_person["id"],
                    to_user_id=to_person["id"],
                    from_label=user_label(from_person),
                    to_label=user_label(to_person),
                    attr_id=attr_id,
                    attr_name=attr_name,
                    model_ids=model_ids,
                    team_id=self.team_id,
                    include_children=self.include_children,
                    authorization={"group_tree": getattr(self.actor, "group_tree", []) or []},
                    status=QUEUED,
                    execution_token=uuid.uuid4().hex,
                    idempotency_key=key,
                    request_hash=digest,
                )
                created = True
                transaction.on_commit(lambda: self.dispatch(str(task.id), task.execution_token))
        task.refresh_from_db()
        return self._task_payload(task), created

    def execute(self, task_id, execution_token):
        task = OwnerHandoverTask.objects.get(pk=task_id)
        if task.execution_token != execution_token:
            logger.info("owner handover ignored stale token, handover_id=%s", task_id)
            return self._task_payload(task)
        if task.status in TERMINAL_STATUSES:
            return self._task_payload(task)
        if task.status == QUEUED:
            claimed = OwnerHandoverTask.objects.filter(pk=task_id, status=QUEUED, execution_token=execution_token).update(
                status=RUNNING,
                started_at=now(),
                lease_expires_at=now() + LEASE,
            )
            if not claimed:
                task.refresh_from_db()
                return self._task_payload(task)
            task.status = RUNNING
        try:
            self._execute(task)
        except OwnerHandoverRejected as exc:
            logger.info(
                "owner handover rejected, handover_id=%s, failed_stage=%s, error_type=%s",
                task_id,
                "execute",
                type(exc).__name__,
            )
            OwnerHandoverTask.objects.filter(pk=task_id, execution_token=execution_token).update(
                status=FAILED,
                message=str(exc.message)[:512],
                finished_at=now(),
            )
        except Exception as exc:
            logger.exception(
                "owner handover failed, handover_id=%s, failed_stage=%s, error_type=%s",
                task_id,
                "execute",
                type(exc).__name__,
            )
            OwnerHandoverTask.objects.filter(pk=task_id, execution_token=execution_token).update(
                status=FAILED,
                message="交接执行失败",
                finished_at=now(),
            )
        task.refresh_from_db()
        return self._task_payload(task)

    def cancel(self, task_id):
        task = self._own_task(task_id)
        if task.status == QUEUED:
            OwnerHandoverTask.objects.filter(pk=task.id, status=QUEUED).update(
                status=CANCELLED,
                message="已取消",
                finished_at=now(),
            )
        elif task.status == RUNNING:
            OwnerHandoverTask.objects.filter(pk=task.id, status=RUNNING).update(cancel_requested=True)
        task.refresh_from_db()
        return self._task_payload(task)

    def get_task(self, task_id):
        return self._task_payload(self._own_task(task_id))

    def list_tasks(self, user_id=None, page=1, page_size=20):
        page = self._page(page)
        page_size = self._page_size(page_size)
        queryset = OwnerHandoverTask.objects.filter(team_id=self.team_id).order_by("-created_at", "-id")
        if user_id not in (None, ""):
            try:
                user_id = int(user_id)
            except (TypeError, ValueError):
                raise OwnerHandoverRejected("user_not_found", "用户不存在")
            if not self.directory.get(user_id):
                raise OwnerHandoverRejected("user_not_found", "用户不存在")
            queryset = queryset.filter(Q(from_user_id=user_id) | Q(to_user_id=user_id))
        total = queryset.count()
        start = (page - 1) * page_size
        items = [self._history_item(task) for task in queryset[start : start + page_size]]
        return {"count": total, "page": page, "page_size": page_size, "items": items}

    def delete_tasks(self, task_ids):
        ids = []
        for item in task_ids or []:
            text = str(item or "").strip()
            if text and text not in ids:
                ids.append(text)
        if not ids:
            raise OwnerHandoverRejected("bad_delete", "请选择要删除的任务")
        if len(ids) > PAGE_SIZE_MAX:
            raise OwnerHandoverRejected("bad_delete", f"一次最多删除 {PAGE_SIZE_MAX} 条")
        queryset = OwnerHandoverTask.objects.filter(pk__in=ids, team_id=self.team_id)
        kept = queryset.filter(status__in=ACTIVE_STATUSES).count()
        terminal = queryset.filter(status__in=TERMINAL_STATUSES)
        deleted = terminal.count()
        terminal.delete()
        logger.info(
            "owner handover tasks deleted, team_id=%s, tasks=%s, kept=%s",
            self.team_id,
            deleted,
            kept,
        )
        return {"deleted": deleted, "kept": kept}

    def list_failures(self, task_id, page=1, page_size=20):
        task = self._own_task(task_id)
        page = self._page(page)
        page_size = self._page_size(page_size)
        queryset = task.failures.order_by("id")
        total = queryset.count()
        start = (page - 1) * page_size
        items = [
            {
                "model_id": row.model_id,
                "model_name": row.model_name,
                "inst_uuid": row.inst_uuid,
                "inst_name": row.inst_name,
                "reason_code": row.reason_code,
                "message": row.message,
            }
            for row in queryset[start : start + page_size]
        ]
        return {"count": total, "page": page, "page_size": page_size, "items": items}

    def list_outcome_statuses(self, task_id, inst_uuids):
        task = self._own_task(task_id)
        uuids = []
        for item in inst_uuids or []:
            for part in str(item or "").split(","):
                text = part.strip()
                if text and text not in uuids:
                    uuids.append(text)
        if len(uuids) > PAGE_SIZE_MAX:
            raise OwnerHandoverRejected("bad_page", f"一次最多查询 {PAGE_SIZE_MAX} 条转移状态")
        found = dict(OwnerHandoverOutcome.objects.filter(task=task, inst_uuid__in=uuids).values_list("inst_uuid", "result"))
        return [{"inst_uuid": inst_uuid, "transfer_status": self._transfer_status(found.get(inst_uuid))} for inst_uuid in uuids]

    @staticmethod
    def _transfer_status(result):
        if result == OUTCOME_SUCCESS:
            return "succeeded"
        if result == OUTCOME_FAILED:
            return "failed"
        return "pending"

    def cleanup_history(self, user_id, days):
        try:
            days = int(days)
        except (TypeError, ValueError):
            raise OwnerHandoverRejected("bad_cleanup", "请选择天数")
        if days < 1 or days > CLEANUP_DAYS_MAX:
            raise OwnerHandoverRejected("bad_cleanup", f"天数必须在 1 到 {CLEANUP_DAYS_MAX} 之间")
        people = self._cleanup_people(user_id)
        cutoff = now() - timedelta(days=days)
        tasks = OwnerHandoverTask.objects.filter(
            team_id=self.team_id,
            status__in=TERMINAL_STATUSES,
            created_at__lt=cutoff,
        )
        if people:
            user_ids = [person["id"] for person in people]
            tasks = tasks.filter(Q(from_user_id__in=user_ids) | Q(to_user_id__in=user_ids))
        task_count = tasks.count()
        tasks.delete()
        from apps.cmdb.models.change_record import OWNER_HANDOVER, ChangeRecord

        records = ChangeRecord.objects.filter(
            scenario=OWNER_HANDOVER,
            created_at__lt=cutoff,
        )
        if people:
            matched = Q()
            for person in people:
                matched |= Q(message__contains=user_label(person))
            records = records.filter(matched)
        record_count = records.count()
        records.delete()
        logger.info(
            "owner handover history cleaned, user_id=%s, days=%s, tasks=%s, records=%s",
            ",".join(str(person["id"]) for person in people) or 0,
            days,
            task_count,
            record_count,
        )
        return {"tasks": task_count, "records": record_count, "days": days}

    def _cleanup_people(self, user_id):
        if user_id in (None, "", []):
            return []
        raw = user_id if isinstance(user_id, (list, tuple)) else [user_id]
        people = []
        seen = set()
        for item in raw:
            if item in (None, ""):
                continue
            try:
                parsed = int(item)
            except (TypeError, ValueError):
                raise OwnerHandoverRejected("bad_cleanup", "请选择用户和天数")
            if parsed in seen:
                continue
            seen.add(parsed)
            person = self.directory.get(parsed)
            if not person:
                raise OwnerHandoverRejected("user_not_found", "用户不存在")
            people.append(person)
        if len(people) > PAGE_SIZE_MAX:
            raise OwnerHandoverRejected("bad_cleanup", f"一次最多选择 {PAGE_SIZE_MAX} 个用户")
        return people

    def _preview_item(self, row, from_person, to_person):
        changes = []
        for change in row["changes"]:
            changes.append(
                {
                    "attr_id": change["attr_id"],
                    "attr_name": change["attr_name"],
                    "before": self._labels(change["before_ids"]),
                    "after": self._labels(change["after_ids"]),
                }
            )
        return {
            "model_id": row["model_id"],
            "model_name": row["model_name"],
            "inst_uuid": row["instance"].get("inst_uuid") or "",
            "inst_name": row["instance"].get("inst_name") or "",
            "organization": organization_label(row["instance"]),
            "changes": changes,
            "from_label": user_label(from_person),
            "to_label": user_label(to_person),
            "transfer_status": "pending",
        }

    def _labels(self, user_ids):
        labels = []
        for user_id in user_ids:
            person = self.directory.get(user_id)
            labels.append(user_label(person) if person else str(user_id))
        return ", ".join(labels)

    def _counts(self, rows):
        bucket = {}
        for row in rows:
            item = bucket.setdefault(row["model_id"], {"model_id": row["model_id"], "model_name": row["model_name"], "count": 0})
            item["count"] += 1
        return list(bucket.values())

    def _require_field(self, attr_id, attr_name):
        attr_id = str(attr_id or "").strip()
        attr_name = str(attr_name or "").strip()
        if not attr_id or not attr_name:
            raise OwnerHandoverRejected("field_required", "请选择用户字段")
        return attr_id, attr_name

    def _select_models(self, model_ids, attr_id, attr_name):
        catalog = self.catalog.list_models()
        by_id = {model["model_id"]: model for model in catalog}
        if not model_ids:
            candidates = list(by_id.values())
            inapplicable = []
        else:
            candidates = []
            inapplicable = []
            for model_id in model_ids:
                model = by_id.get(model_id)
                if model:
                    candidates.append(model)
                else:
                    inapplicable.append({"model_id": model_id, "model_name": model_id})
        selected = []
        for model in candidates:
            fields = [field for field in model["fields"] if field.get("attr_id") == attr_id and field.get("attr_name") == attr_name]
            if fields:
                selected.append({**model, "fields": fields})
            elif model_ids:
                inapplicable.append({"model_id": model["model_id"], "model_name": model["model_name"]})
        return selected, inapplicable

    def _require_people(self, from_user_id, to_user_id):
        try:
            from_user_id = int(from_user_id)
            to_user_id = int(to_user_id)
        except (TypeError, ValueError):
            raise OwnerHandoverRejected("user_not_found", "负责人不存在")
        if from_user_id == to_user_id:
            raise OwnerHandoverRejected("same_user", "原负责人和新负责人不能是同一个人")
        from_person = self.directory.get(from_user_id)
        to_person = self.directory.get(to_user_id)
        if not from_person or not to_person:
            raise OwnerHandoverRejected("user_not_found", "负责人不存在")
        self._require_target(to_person)
        return from_person, to_person

    def _require_target(self, person):
        if person.get("disabled") or person.get("employment_status") == EmploymentStatus.RESIGNED:
            raise OwnerHandoverRejected("target_inactive", "新负责人必须是未禁用且未离职的用户")

    def _load_token(self, token):
        try:
            payload = signing.loads(token, salt=PREVIEW_SALT, max_age=PREVIEW_MAX_AGE)
        except signing.SignatureExpired:
            raise OwnerHandoverRejected("preview_expired", "预览已过期，请重新预览")
        except signing.BadSignature:
            raise OwnerHandoverRejected("preview_mismatch", "预览已失效，请重新预览")
        domain = getattr(self.actor, "domain", "domain.com")
        if payload.get("operator") != self.actor.username or payload.get("domain") != domain:
            raise OwnerHandoverRejected("preview_mismatch", "预览已失效，请重新预览")
        if int(payload.get("team_id")) != self.team_id or bool(payload.get("include_children")) != self.include_children:
            raise OwnerHandoverRejected("preview_mismatch", "组织范围已变化，请重新预览")
        return payload

    def _request_hash(self, from_user_id, to_user_id, model_ids, attr_id, attr_name):
        raw = json.dumps(
            {
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
                "attr_id": attr_id,
                "attr_name": attr_name,
                "model_ids": list(model_ids),
                "team_id": self.team_id,
                "include_children": self.include_children,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _own_task(self, task_id):
        task = OwnerHandoverTask.objects.filter(
            pk=task_id,
            operator_username=self.actor.username,
            operator_domain=getattr(self.actor, "domain", "domain.com"),
        ).first()
        if task is None:
            raise OwnerHandoverRejected("not_found", "交接任务不存在", 404)
        return task

    def _task_payload(self, task):
        return {
            "id": str(task.id),
            "status": task.status,
            "from_user_id": task.from_user_id,
            "to_user_id": task.to_user_id,
            "from_label": task.from_label,
            "to_label": task.to_label,
            "attr_id": task.attr_id,
            "attr_name": task.attr_name,
            "model_ids": task.model_ids,
            "total_count": task.total_count,
            "success_count": task.success_count,
            "skipped_count": task.skipped_count,
            "failed_count": task.failed_count,
            "message": task.message,
        }

    def _history_item(self, task):
        return {
            **self._task_payload(task),
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "operator_username": task.operator_username,
        }

    @staticmethod
    def _page(value):
        try:
            page = int(value or 1)
        except (TypeError, ValueError):
            raise OwnerHandoverRejected("bad_page", "页码必须是整数")
        if page < 1:
            raise OwnerHandoverRejected("bad_page", "页码必须大于等于 1")
        return page

    @staticmethod
    def _page_size(value):
        try:
            size = int(value or 20)
        except (TypeError, ValueError):
            raise OwnerHandoverRejected("bad_page", "分页大小必须是整数")
        if size < 1 or size > PAGE_SIZE_MAX:
            raise OwnerHandoverRejected("bad_page", f"分页大小必须在 1 到 {PAGE_SIZE_MAX} 之间")
        return size


def dispatch_owner_handover(task_id, execution_token):
    from django.conf import settings

    from apps.cmdb.tasks.owner_handover import execute_owner_handover

    if getattr(settings, "IS_USE_CELERY", False):
        execute_owner_handover.delay(str(task_id), execution_token)
        return
    execute_owner_handover(str(task_id), execution_token)


def execute_saved_task(task_id, execution_token):
    task = OwnerHandoverTask.objects.filter(pk=task_id).first()
    if task is None or task.execution_token != execution_token:
        logger.info("owner handover ignored stale token, handover_id=%s", task_id)
        return
    user_model = get_user_model()
    user = user_model.objects.filter(username=task.operator_username, domain=task.operator_domain).first()
    if user is None:
        OwnerHandoverTask.objects.filter(pk=task.pk, execution_token=execution_token).update(
            status=FAILED,
            message="执行人已不存在",
            finished_at=now(),
        )
        return
    if not getattr(user, "group_tree", None):
        user.group_tree = (task.authorization or {}).get("group_tree") or []
    service = OwnerHandoverService.for_actor(user, task.team_id, task.include_children, dispatch=lambda *_args: None)
    service.execute(task_id, execution_token)
