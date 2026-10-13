"""作业模板版本快照。

版本号按 Asia/Shanghai 的日期生成：当天第一条为 vYYYY.MM.DD，之后为 .2、.3。
当前模板行仍是执行入口；恢复会写回当前行并追加一条新版本。
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import zipfile
from copy import deepcopy
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.job_mgmt.models import Playbook, PlaybookRevision, Script, ScriptRevision
from apps.job_mgmt.services.param_crypto import ParamCrypto
from apps.job_mgmt.utils.playbook_archive import open_archive

SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50
MAX_COMPARE_TEXT_BYTES = 1024 * 1024


class RevisionNotFound(Exception):
    """版本不存在，或不属于当前模板。"""


class RevisionAlreadyCurrent(Exception):
    """所选版本已经是当前版本。"""


def annotate_current_revision_label(queryset, revision_model, relation: str):
    """列表只取最新版本号。没有历史时不补快照。"""
    latest_label = revision_model.objects.filter(**{relation: OuterRef("pk")}).order_by("-created_at", "-id").values("label")[:1]
    return queryset.annotate(current_revision_label=Subquery(latest_label))


def display_revision_label(instance) -> str:
    """有历史用最新版本号；否则按更新时间给出第一次打开抽屉时会出现的版本号。"""
    annotated = "current_revision_label" in getattr(instance, "__dict__", {})
    if annotated:
        label = instance.__dict__.get("current_revision_label")
        if label:
            return label
    else:
        stored = _stored_revision_label(instance)
        if stored:
            return stored
    when = instance.updated_at or instance.created_at
    if when is None:
        return ""
    return version_label(when, [])


def _stored_revision_label(instance) -> str:
    if isinstance(instance, Playbook):
        queryset = PlaybookRevision.objects.filter(playbook_id=instance.pk)
    elif isinstance(instance, Script):
        queryset = ScriptRevision.objects.filter(script_id=instance.pk)
    else:
        return ""
    label = queryset.order_by("-created_at", "-id").values_list("label", flat=True).first()
    return label or ""


def version_label(when, existing_labels) -> str:
    """同一模板、同一天的第一条不带后缀，其后从 .2 开始。"""
    if timezone.is_naive(when):
        when = timezone.make_aware(when, timezone.get_current_timezone())
    base = f"v{when.astimezone(SHANGHAI):%Y.%m.%d}"
    existing = set(existing_labels)
    if base not in existing:
        return base
    index = 2
    while f"{base}.{index}" in existing:
        index += 1
    return f"{base}.{index}"


def payload_hash(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def request_operator(serializer) -> str:
    request = getattr(serializer, "context", {}).get("request")
    user = getattr(request, "user", None)
    return getattr(user, "username", "") or ""


def parse_page(page, page_size) -> tuple[int, int]:
    try:
        parsed_page = int(page)
        parsed_size = int(page_size)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid page") from exc
    if parsed_page < 1 or parsed_size < 1:
        raise ValueError("invalid page")
    return parsed_page, min(parsed_size, MAX_PAGE_SIZE)


def script_payload(script) -> dict:
    return {
        "name": script.name,
        "description": script.description or "",
        "script_type": script.script_type,
        "content": script.content or "",
        "params": deepcopy(script.params or []),
        "timeout": script.timeout,
    }


class TemplateRevisionService:
    """脚本库与 Playbook 库共用的版本写入、对比和恢复。"""

    @staticmethod
    def capture_script(script, *, operator="", before=None, before_at=None, before_by=""):
        """成功写入脚本后调用。首次变更会先补上变更前的快照。"""
        with transaction.atomic():
            locked = Script.objects.select_for_update().get(pk=script.pk)
            current = script_payload(locked)
            current_hash = payload_hash(current)
            if not ScriptRevision.objects.filter(script=locked).exists() and before is not None:
                TemplateRevisionService._capture_first_script(
                    locked,
                    current,
                    current_hash,
                    before,
                    before_at=before_at,
                    before_by=before_by,
                    operator=operator,
                )
                return
            latest = _latest_script(locked)
            if latest is not None and latest.content_hash == current_hash:
                return
            _insert_script(locked, current, when=timezone.now(), operator=operator)

    @staticmethod
    def _capture_first_script(script, current, current_hash, before, *, before_at, before_by, operator):
        stamp = before_at or script.created_at
        before_hash = payload_hash(before)
        if before_hash == current_hash:
            _insert_script(script, current, when=stamp, operator=before_by or operator)
            return
        _insert_script(script, before, when=stamp, operator=before_by or "")
        _insert_script(script, current, when=timezone.now(), operator=operator or "")

    @staticmethod
    def ensure_script_history(script):
        """没有历史时，用当前内容补一条，时间用模板的更新时间。"""
        if ScriptRevision.objects.filter(script_id=script.pk).exists():
            return
        with transaction.atomic():
            locked = Script.objects.select_for_update().get(pk=script.pk)
            if ScriptRevision.objects.filter(script=locked).exists():
                return
            _insert_script(
                locked,
                script_payload(locked),
                when=locked.updated_at or locked.created_at,
                operator=locked.updated_by or locked.created_by or "",
            )

    @staticmethod
    def list_script_revisions(script, page, page_size) -> dict:
        TemplateRevisionService.ensure_script_history(script)
        return _list_revisions(ScriptRevision.objects.filter(script=script), page, page_size)

    @staticmethod
    def compare_script(script, revision_id) -> dict:
        TemplateRevisionService.ensure_script_history(script)
        selected = ScriptRevision.objects.filter(script=script, pk=revision_id).first()
        if selected is None:
            raise RevisionNotFound
        current = _latest_script(script)
        return {
            "current": _revision_meta(current),
            "selected": _revision_meta(selected),
            "fields": _field_diffs(
                [
                    ("name", selected.name, current.name),
                    ("description", selected.description, current.description),
                    ("script_type", selected.script_type, current.script_type),
                    ("timeout", selected.timeout, current.timeout),
                ]
            ),
            "content": {"selected": selected.content, "current": current.content},
            "params": _param_diffs(selected.params or [], current.params or []),
        }

    @staticmethod
    def restore_script(script, revision, operator):
        with transaction.atomic():
            locked = Script.objects.select_for_update().get(pk=script.pk)
            if revision.script_id != locked.id:
                raise RevisionNotFound
            latest = _latest_script(locked)
            if latest is not None and latest.id == revision.id:
                raise RevisionAlreadyCurrent
            locked.name = revision.name
            locked.description = revision.description
            locked.script_type = revision.script_type
            locked.content = revision.content
            locked.params = revision.params
            locked.timeout = revision.timeout
            locked.updated_by = operator or ""
            locked.save(update_fields=["name", "description", "script_type", "content", "params", "timeout", "updated_by", "updated_at"])
            TemplateRevisionService.capture_script(locked, operator=operator or "")
            return locked

    @staticmethod
    def playbook_state(playbook):
        return _load_playbook(playbook)

    @staticmethod
    def capture_playbook(playbook, *, operator="", before=None, before_bytes=None, before_name="", before_at=None, before_by=""):
        """成功写入 Playbook 后调用。升级前也应先调用一次，保留即将被替换的压缩包。"""
        with transaction.atomic():
            locked = Playbook.objects.select_for_update().get(pk=playbook.pk)
            current, current_bytes, current_name = _load_playbook(locked)
            current_hash = payload_hash(current)
            if not PlaybookRevision.objects.filter(playbook=locked).exists() and before is not None:
                TemplateRevisionService._capture_first_playbook(
                    locked,
                    current,
                    current_bytes,
                    current_name,
                    current_hash,
                    before,
                    before_bytes=before_bytes,
                    before_name=before_name,
                    before_at=before_at,
                    before_by=before_by,
                    operator=operator,
                )
                return
            latest = _latest_playbook(locked)
            if latest is not None and latest.content_hash == current_hash:
                return
            _insert_playbook(locked, current, current_bytes, current_name, when=timezone.now(), operator=operator)

    @staticmethod
    def _capture_first_playbook(
        playbook,
        current,
        current_bytes,
        current_name,
        current_hash,
        before,
        *,
        before_bytes,
        before_name,
        before_at,
        before_by,
        operator,
    ):
        stamp = before_at or playbook.created_at
        blob = current_bytes if before_bytes is None else before_bytes
        blob_name = before_name or current_name
        if payload_hash(before) == current_hash:
            _insert_playbook(playbook, current, current_bytes, current_name, when=stamp, operator=before_by or operator)
            return
        _insert_playbook(playbook, before, blob, blob_name, when=stamp, operator=before_by or "")
        _insert_playbook(playbook, current, current_bytes, current_name, when=timezone.now(), operator=operator or "")

    @staticmethod
    def ensure_playbook_history(playbook):
        if PlaybookRevision.objects.filter(playbook_id=playbook.pk).exists():
            return
        with transaction.atomic():
            locked = Playbook.objects.select_for_update().get(pk=playbook.pk)
            if PlaybookRevision.objects.filter(playbook=locked).exists():
                return
            payload, data, filename = _load_playbook(locked)
            _insert_playbook(
                locked,
                payload,
                data,
                filename,
                when=locked.updated_at or locked.created_at,
                operator=locked.updated_by or locked.created_by or "",
            )

    @staticmethod
    def list_playbook_revisions(playbook, page, page_size) -> dict:
        TemplateRevisionService.ensure_playbook_history(playbook)
        return _list_revisions(PlaybookRevision.objects.filter(playbook=playbook), page, page_size)

    @staticmethod
    def compare_playbook(playbook, revision_id) -> dict:
        TemplateRevisionService.ensure_playbook_history(playbook)
        selected = PlaybookRevision.objects.filter(playbook=playbook, pk=revision_id).first()
        if selected is None:
            raise RevisionNotFound
        current = _latest_playbook(playbook)
        selected_files, selected_error = _read_archive(selected.file)
        current_files, current_error = _read_archive(current.file)
        archive_error = ""
        if selected_error and current_error:
            archive_error = "both"
        elif selected_error:
            archive_error = "selected"
        elif current_error:
            archive_error = "current"
        return {
            "current": _revision_meta(current),
            "selected": _revision_meta(selected),
            "fields": _field_diffs(
                [
                    ("name", selected.name, current.name),
                    ("description", selected.description, current.description),
                ]
            ),
            "readme": {"selected": selected.readme, "current": current.readme},
            "params": _param_diffs(selected.params or [], current.params or []),
            "files": [] if archive_error else _file_diffs(selected_files, current_files),
            "archive_error": archive_error,
        }

    @staticmethod
    def restore_playbook(playbook, revision, operator):
        with transaction.atomic():
            locked = Playbook.objects.select_for_update().get(pk=playbook.pk)
            if revision.playbook_id != locked.id:
                raise RevisionNotFound
            latest = _latest_playbook(locked)
            if latest is not None and latest.id == revision.id:
                raise RevisionAlreadyCurrent
            old_name = locked.file.name if locked.file else ""
            locked.name = revision.name
            locked.description = revision.description
            locked.version = revision.version
            locked.readme = revision.readme
            locked.file_list = revision.file_list
            locked.params = revision.params
            locked.updated_by = operator or ""
            _replace_playbook_file(locked, revision, old_name)
            locked.save(
                update_fields=[
                    "name",
                    "description",
                    "version",
                    "readme",
                    "file_list",
                    "params",
                    "file",
                    "updated_by",
                    "updated_at",
                ]
            )
            TemplateRevisionService.capture_playbook(locked, operator=operator or "")
            return locked


def _capture_operator(operator) -> str:
    return operator or ""


def _insert_script(script, payload, *, when, operator):
    labels = ScriptRevision.objects.filter(script=script).values_list("label", flat=True)
    return ScriptRevision.objects.create(
        script=script,
        label=version_label(when, labels),
        name=payload["name"],
        description=payload["description"],
        script_type=payload["script_type"],
        content=payload["content"],
        params=payload["params"],
        timeout=payload["timeout"],
        content_hash=payload_hash(payload),
        created_at=when,
        created_by=_capture_operator(operator),
    )


def _insert_playbook(playbook, payload, data, filename, *, when, operator):
    labels = PlaybookRevision.objects.filter(playbook=playbook).values_list("label", flat=True)
    revision = PlaybookRevision.objects.create(
        playbook=playbook,
        label=version_label(when, labels),
        name=payload["name"],
        description=payload["description"],
        version=payload["version"],
        readme=payload["readme"],
        file_list=payload["file_list"],
        params=payload["params"],
        file_sha256=payload["file_sha256"],
        content_hash=payload_hash(payload),
        created_at=when,
        created_by=_capture_operator(operator),
    )
    if data:
        revision.file.save(filename or "playbook.zip", ContentFile(data), save=True)
    return revision


def _latest_script(script):
    return ScriptRevision.objects.filter(script=script).order_by("-created_at", "-id").first()


def _latest_playbook(playbook):
    return PlaybookRevision.objects.filter(playbook=playbook).order_by("-created_at", "-id").first()


def _iso(value):
    if value is None:
        return None
    return value.isoformat()


def _list_revisions(queryset, page, page_size) -> dict:
    ordered = queryset.order_by("-created_at", "-id")
    total = ordered.count()
    current_id = ordered.values_list("id", flat=True).first()
    start = (page - 1) * page_size
    rows = list(ordered[start : start + page_size])
    return {
        "count": total,
        "items": [
            {
                "id": row.id,
                "label": row.label,
                "created_at": _iso(row.created_at),
                "created_by": row.created_by,
                "is_current": row.id == current_id,
            }
            for row in rows
        ],
    }


def _revision_meta(revision) -> dict:
    return {
        "id": revision.id,
        "label": revision.label,
        "created_at": _iso(revision.created_at),
        "created_by": revision.created_by,
    }


def _field_diffs(pairs) -> list:
    return [{"key": key, "selected": selected, "current": current, "changed": selected != current} for key, selected, current in pairs]


def _param_diffs(selected_params, current_params) -> list:
    selected_by_name = {_param_name(item): item for item in selected_params if isinstance(item, dict)}
    current_by_name = {_param_name(item): item for item in current_params if isinstance(item, dict)}
    names = []
    for item in selected_params:
        if isinstance(item, dict) and _param_name(item) not in names:
            names.append(_param_name(item))
    for item in current_params:
        if isinstance(item, dict) and _param_name(item) not in names:
            names.append(_param_name(item))

    rows = []
    for name in names:
        selected = selected_by_name.get(name)
        current = current_by_name.get(name)
        if selected is None:
            status = "added"
        elif current is None:
            status = "removed"
        else:
            status = "modified" if _param_changed(selected, current) else "unchanged"
        default_changed = _raw_default(selected) != _raw_default(current)
        rows.append(
            {
                "name": name,
                "status": status,
                "default_changed": default_changed,
                "selected": _public_param(selected),
                "current": _public_param(current),
            }
        )
    return rows


def _param_name(param) -> str:
    return str(param.get("name") or "")


def _raw_default(param):
    if not param:
        return None
    return param.get("default")


def _param_changed(selected, current) -> bool:
    left = _public_param(selected)
    right = _public_param(current)
    if left != right:
        return True
    return _raw_default(selected) != _raw_default(current)


def _public_param(param):
    if not param:
        return None
    masked = ParamCrypto.mask_encrypted_defaults([dict(param)])[0]
    return {
        "name": masked.get("name") or "",
        "label": masked.get("label") or "",
        "description": masked.get("description") or "",
        "type": masked.get("type") or "text",
        "options": masked.get("options") or [],
        "is_required": bool(masked.get("is_required")),
        "is_encrypted": bool(masked.get("is_encrypted")),
        "default": masked.get("default") or "",
    }


def _load_playbook(playbook):
    digest, data, filename = _read_stored_file(playbook.file)
    payload = {
        "name": playbook.name,
        "description": playbook.description or "",
        "version": playbook.version or "",
        "readme": playbook.readme or "",
        "file_list": deepcopy(playbook.file_list or []),
        "params": deepcopy(playbook.params or []),
        "file_sha256": digest,
    }
    return payload, data, filename


def _read_stored_file(file_field):
    if not file_field:
        return "", b"", ""
    file_field.open("rb")
    try:
        data = file_field.read()
    finally:
        file_field.close()
    filename = os.path.basename(file_field.name or "") or "playbook.zip"
    return hashlib.sha256(data).hexdigest(), data, filename


def _replace_playbook_file(playbook, revision, old_name):
    """把历史压缩包复制为当前包。新路径带随机名，避免覆盖或删掉刚写回的对象。"""
    storage = Playbook._meta.get_field("file").storage
    digest, data, filename = _read_stored_file(revision.file)
    if data:
        stored_name = f"{digest[:12]}_{filename}"
        playbook.file.save(stored_name, ContentFile(data), save=False)
    elif playbook.file:
        playbook.file.delete(save=False)
    new_name = playbook.file.name if playbook.file else ""
    if old_name and old_name != new_name:
        storage.delete(old_name)


def _read_archive(file_field):
    if not file_field:
        return {}, False
    try:
        return _archive_members(file_field), False
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError):
        return {}, True


def _archive_members(file_field) -> dict:
    members = {}
    with open_archive(file_field) as (archive_type, archive):
        if archive_type == "zip":
            for info in archive.infolist():
                if info.is_dir():
                    continue
                members[info.filename] = archive.read(info.filename)
        else:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                extracted = archive.extractfile(member)
                members[member.name] = extracted.read() if extracted is not None else b""
    return members


def _file_diffs(selected_files, current_files) -> list:
    paths = sorted(set(selected_files) | set(current_files))
    rows = []
    for path in paths:
        selected_raw = selected_files.get(path)
        current_raw = current_files.get(path)
        selected = _member_view(selected_raw) if selected_raw is not None else None
        current = _member_view(current_raw) if current_raw is not None else None
        if selected_raw is None:
            status = "added"
        elif current_raw is None:
            status = "removed"
        elif selected_raw != current_raw:
            status = "modified"
        else:
            status = "unchanged"
        binary = any(item["binary"] for item in (selected, current) if item)
        too_large = any(item["too_large"] for item in (selected, current) if item)
        show_text = status != "unchanged" and not binary and not too_large
        rows.append(
            {
                "path": path,
                "status": status,
                "binary": binary,
                "too_large": too_large,
                "selected_size": None if selected is None else selected["size"],
                "current_size": None if current is None else current["size"],
                "selected_text": selected["text"] if show_text and selected else "",
                "current_text": current["text"] if show_text and current else "",
            }
        )
    return rows


def _member_view(data: bytes) -> dict:
    size = len(data)
    if size > MAX_COMPARE_TEXT_BYTES:
        return {"size": size, "text": "", "binary": False, "too_large": True}
    if b"\x00" in data:
        return {"size": size, "text": "", "binary": True, "too_large": False}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"size": size, "text": "", "binary": True, "too_large": False}
    return {"size": size, "text": text, "binary": False, "too_large": False}
