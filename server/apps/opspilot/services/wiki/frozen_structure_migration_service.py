"""存量知识库补齐冻结六根，并把空简介从旧 Purpose 回填。"""

from __future__ import annotations

import re
import unicodedata
from copy import deepcopy

from django.db import transaction
from django.db.models import Max

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import WikiDirectory, WikiKnowledgeBase
from apps.opspilot.services.wiki.generation_service import GenerationServiceError
from apps.opspilot.services.wiki.purpose_schema_service import (
    FROZEN_PAGE_TYPES,
    FROZEN_ROOTS,
    FROZEN_ROOT_BY_KEY,
    FROZEN_ROOT_KEYS,
    normalize_folder_name,
)
from apps.opspilot.services.wiki.structure_service import (
    StructureServiceError,
    get_structure,
    save_structure,
)

_HEADING_RE = re.compile(r"^#{1,6}\s+")
_MARKDOWN_MARK_RE = re.compile(r"[*_`>#\[\]()]+")


def introduction_from_purpose(purpose_md, fallback_name=""):
    """取 Purpose 首个非标题段，去掉 Markdown 标记；仍空则用知识库名。"""

    for raw_line in str(purpose_md or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _HEADING_RE.match(line):
            continue
        cleaned = _MARKDOWN_MARK_RE.sub("", line)
        cleaned = re.sub(r"^[-*]\s+", "", cleaned).strip()
        if cleaned:
            return cleaned
    return unicodedata.normalize("NFKC", str(fallback_name or "")).strip() or "知识库"


def _actor(operator=""):
    return unicodedata.normalize("NFKC", str(operator or "")).strip()[:32] or "system"


def _freeze_directory(directory, spec, actor):
    updates = []
    if directory.key != spec["key"]:
        directory.key = spec["key"]
        updates.append("key")
    if directory.name != spec["name"]:
        directory.name = spec["name"]
        updates.append("name")
    if directory.origin != "system":
        directory.origin = "system"
        updates.append("origin")
    if directory.status != "active":
        directory.status = "active"
        updates.append("status")
    accepts_pages = bool(spec.get("accepts_pages", True))
    if directory.accepts_pages != accepts_pages:
        directory.accepts_pages = accepts_pages
        updates.append("accepts_pages")
    if directory.parent_id is not None:
        directory.parent = None
        updates.append("parent")
    if directory.merged_into_id is not None:
        directory.merged_into = None
        updates.append("merged_into")
    if updates:
        directory.updated_by = actor
        directory.save(update_fields=[*updates, "updated_by", "updated_at"])
    return bool(updates)


def _root_name_matches(directory, spec):
    return directory.parent_id is None and directory.status == "active" and normalize_folder_name(directory.name) == normalize_folder_name(spec["name"])


def _ensure_frozen_directories(knowledge_base, actor):
    changed = False
    directories = list(WikiDirectory.objects.filter(knowledge_base=knowledge_base).order_by("id"))
    by_key = {directory.key: directory for directory in directories}
    used_ids = set()
    for spec in FROZEN_ROOTS:
        existing = by_key.get(spec["key"])
        if existing is None:
            existing = next((item for item in directories if item.pk not in used_ids and _root_name_matches(item, spec)), None)
        if existing is None:
            sort_order = (WikiDirectory.objects.filter(knowledge_base=knowledge_base).aggregate(value=Max("sort_order"))["value"] or 0) + 10
            existing = WikiDirectory.objects.create(
                knowledge_base=knowledge_base,
                key=spec["key"],
                name=spec["name"],
                description=spec["description"],
                parent=None,
                sort_order=sort_order,
                origin="system",
                status="active",
                accepts_pages=bool(spec.get("accepts_pages", True)),
                merged_into=None,
                created_by=actor,
                updated_by=actor,
            )
            directories.append(existing)
            by_key[existing.key] = existing
            changed = True
        else:
            changed = _freeze_directory(existing, spec, actor) or changed
            by_key[existing.key] = existing
        used_ids.add(existing.pk)
    return changed


def _frozen_rules(spec):
    page_type = spec.get("page_type")
    allowed = [page_type] if page_type else []
    return {"allowed_page_types": allowed, "default_for_page_types": list(allowed)}


def _sanitize_existing_rules(rules, allowed_types):
    allowed_lookup = {item.casefold(): item for item in allowed_types}
    frozen_defaults = {item.casefold() for item in FROZEN_PAGE_TYPES}
    raw = rules or {}
    allowed = []
    seen = set()
    for item in raw.get("allowed_page_types") or []:
        canonical = allowed_lookup.get(str(item or "").strip().casefold())
        if canonical is None or canonical.casefold() in seen:
            continue
        seen.add(canonical.casefold())
        allowed.append(canonical)
    defaults = []
    seen_defaults = set()
    for item in raw.get("default_for_page_types") or []:
        canonical = allowed_lookup.get(str(item or "").strip().casefold())
        if (
            canonical is None
            or canonical.casefold() in seen_defaults
            or canonical.casefold() in frozen_defaults
            or canonical.casefold() not in seen
        ):
            continue
        seen_defaults.add(canonical.casefold())
        defaults.append(canonical)
    return {"allowed_page_types": allowed, "default_for_page_types": defaults}


def _snapshot_lacks_frozen_roots(knowledge_base):
    revision = getattr(knowledge_base, "active_structure_revision", None)
    if revision is None:
        return True
    keys = {
        item.get("key")
        for item in (revision.structure_snapshot or {}).get("directories") or []
        if item.get("parent") is None
    }
    return not FROZEN_ROOT_KEYS <= keys


def _merged_page_types(current_types):
    merged = []
    seen = set()
    for page_type in [*FROZEN_PAGE_TYPES, *(current_types or [])]:
        item = str(page_type or "").strip()
        if not item or item.casefold() == "source" or item.casefold() in seen:
            continue
        seen.add(item.casefold())
        merged.append(item)
    return merged


def _activate_frozen_revision(knowledge_base, actor):
    current = get_structure(knowledge_base)
    if current["structure_revision"] is None or current["active_generation"] is None:
        return False
    page_types = _merged_page_types(current["structure"].get("page_types"))
    snapshot_by_id = {item["id"]: deepcopy(item) for item in current["structure"]["directories"] if type(item.get("id")) is int}
    directories = list(WikiDirectory.objects.filter(knowledge_base=knowledge_base, status="active").select_related("parent").order_by("id"))
    payload_dirs = []
    for directory in directories:
        spec = FROZEN_ROOT_BY_KEY.get(directory.key)
        previous = snapshot_by_id.get(directory.pk)
        node = {
            "kind": "existing",
            "id": directory.pk,
            "key": directory.key,
            "origin": directory.origin,
            "status": directory.status,
            "name": directory.name,
            "description": spec["description"] if spec else (previous or {}).get("description", directory.description or ""),
            "order": (previous or {}).get("order", directory.sort_order),
            "rules": _frozen_rules(spec) if spec else _sanitize_existing_rules((previous or {}).get("rules"), page_types),
            "parent": {"id": directory.parent_id, "key": directory.parent.key} if directory.parent_id else None,
        }
        payload_dirs.append(node)
    payload = {
        "structure_version": current["structure_revision"]["version"],
        "base_generation_id": current["active_generation"]["id"],
        "structure": {
            "format_version": 1,
            "page_types": page_types,
            "directories": payload_dirs,
        },
    }
    save_structure(knowledge_base, payload, operator=actor)
    return True


@transaction.atomic
def ensure_frozen_structure(knowledge_base, *, operator=""):
    """幂等：补齐冻结根、回填简介，并在结构变化时激活新修订。"""

    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    locked = WikiKnowledgeBase.objects.select_for_update().filter(pk=knowledge_base_id).first()
    if locked is None:
        raise StructureServiceError("knowledge_base_not_found", "知识库不存在", status_code=404)
    actor = _actor(operator)
    changed = False
    if not str(locked.introduction or "").strip():
        locked.introduction = introduction_from_purpose(locked.purpose_md, locked.name)
        locked.updated_by = actor
        locked.save(update_fields=["introduction", "updated_by", "updated_at"])
        changed = True
    dirs_changed = _ensure_frozen_directories(locked, actor)
    locked.refresh_from_db()
    has_pair = bool(locked.active_structure_revision_id and locked.active_generation_id)
    revision_needed = has_pair and (dirs_changed or _snapshot_lacks_frozen_roots(locked))
    if revision_needed:
        try:
            _activate_frozen_revision(locked, actor)
            changed = True
        except (StructureServiceError, GenerationServiceError):
            logger.exception("wiki_frozen_structure_revision_failed kb_id=%s", locked.pk)
            changed = changed or dirs_changed
    elif dirs_changed:
        logger.info("wiki_frozen_structure_dirs_without_active_pair kb_id=%s", locked.pk)
    applied = changed or dirs_changed
    if applied:
        logger.info("wiki_frozen_structure_applied kb_id=%s", locked.pk)
    return {"knowledge_base_id": locked.pk, "changed": applied}


def frozen_structure_missing(knowledge_base):
    if not str(getattr(knowledge_base, "introduction", "") or "").strip():
        return True
    existing = set(
        WikiDirectory.objects.filter(
            knowledge_base=knowledge_base,
            status="active",
            parent__isnull=True,
            key__in=FROZEN_ROOT_KEYS,
        ).values_list("key", flat=True)
    )
    return not FROZEN_ROOT_KEYS <= existing


def ensure_frozen_structure_if_needed(knowledge_base, *, operator=""):
    if not frozen_structure_missing(knowledge_base):
        return {"knowledge_base_id": getattr(knowledge_base, "pk", knowledge_base), "changed": False}
    return ensure_frozen_structure(knowledge_base, operator=operator)


def ensure_all_frozen_structures(*, operator="", knowledge_base_ids=None):
    queryset = WikiKnowledgeBase.objects.order_by("id")
    if knowledge_base_ids:
        queryset = queryset.filter(pk__in=list(knowledge_base_ids))
    results = []
    for knowledge_base_id in queryset.values_list("id", flat=True):
        try:
            results.append(ensure_frozen_structure(knowledge_base_id, operator=operator))
        except StructureServiceError as error:
            logger.exception("wiki_frozen_structure_kb_failed kb_id=%s", knowledge_base_id)
            results.append({"knowledge_base_id": knowledge_base_id, "changed": False, "error": error.code})
    return results
