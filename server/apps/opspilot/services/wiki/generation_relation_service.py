"""Generation-scoped deterministic Wiki relation materialization."""

from itertools import combinations

from django.db import transaction

from apps.opspilot.models import PageEvidence, PageRelation, WikiGeneration, WikiKnowledgeBase
from apps.opspilot.services.wiki.relation_service import LINK_RE
from apps.opspilot.services.wiki.title_service import canonical_title


class GenerationRelationError(Exception):
    def __init__(self, code, message, *, details=None):
        self.code = str(code)
        self.details = dict(details or {})
        super().__init__(message)


def _link_key(knowledge_base, value):
    normalized = canonical_title(knowledge_base, value) or (value or "").strip()
    return "".join(char for char in normalized.casefold() if not char.isspace() and char not in "-_\\/")


@transaction.atomic
def rebuild_generation_relations(
    candidate_id,
    *,
    pending_material_ids_by_page=None,
    replace_material_ids_for_pages=None,
):
    """Replace relations of one preparing candidate without touching active data."""

    identity = WikiGeneration.objects.filter(pk=candidate_id).values("id", "knowledge_base_id").first()
    if identity is None:
        raise GenerationRelationError(
            "generation_not_found",
            "generation 不存在",
            details={"generation_id": candidate_id},
        )
    knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=identity["knowledge_base_id"])
    candidate = WikiGeneration.objects.select_for_update().get(pk=candidate_id, knowledge_base=knowledge_base)
    if candidate.status != "preparing":
        raise GenerationRelationError(
            "generation_status_conflict",
            "只有 preparing generation 可以重建关系",
            details={"generation_id": candidate.pk, "status": candidate.status},
        )

    rows = []
    by_exact = {}
    by_key = {}
    for member in candidate.page_members.select_related("page", "page_version").order_by("page_id"):
        display = member.page_display_snapshot or {}
        title = (display.get("title") or member.page.title or "").strip()
        row = {
            "page_id": member.page_id,
            "title": title,
            "body": member.page_version.body or "",
        }
        rows.append(row)
        by_exact.setdefault(title, []).append(row)
        by_key.setdefault(_link_key(knowledge_base, title), []).append(row)

    def lookup(title):
        exact = by_exact.get((title or "").strip())
        if exact:
            return exact
        return by_key.get(_link_key(knowledge_base, title), [])

    pending = {
        int(page_id): {int(material_id) for material_id in material_ids if material_id}
        for page_id, material_ids in (pending_material_ids_by_page or {}).items()
    }
    replace_pages = {int(page_id) for page_id in (replace_material_ids_for_pages or ())}
    material_ids_by_page = {
        row["page_id"]: (
            pending.get(row["page_id"], set())
            if row["page_id"] in replace_pages
            else set(PageEvidence.objects.filter(page_id=row["page_id"]).values_list("material_id", flat=True)) | pending.get(row["page_id"], set())
        )
        for row in rows
    }

    relations = []
    relation_keys = set()
    for left, right in combinations(rows, 2):
        shared = material_ids_by_page[left["page_id"]] & material_ids_by_page[right["page_id"]]
        if not shared:
            continue
        left_id, right_id = sorted((left["page_id"], right["page_id"]))
        relation_keys.add((left_id, right_id, "shared_source"))
        relations.append(
            PageRelation(
                generation=candidate,
                from_page_id=left_id,
                to_page_id=right_id,
                relation_type="shared_source",
                weight=float(len(shared)),
                via_material_id=min(shared),
            )
        )

    issues = []
    for source in rows:
        seen_targets = set()
        for match in LINK_RE.finditer(source["body"]):
            title = match.group(1).strip()
            candidates = [row for row in lookup(title) if row["page_id"] != source["page_id"]]
            if len(candidates) != 1:
                issues.append(
                    {
                        "code": "ambiguous_link" if candidates else "broken_relation",
                        "from_page_id": source["page_id"],
                        "target": title,
                        "candidate_page_ids": [row["page_id"] for row in candidates],
                    }
                )
                continue
            target_id = candidates[0]["page_id"]
            if target_id in seen_targets:
                continue
            seen_targets.add(target_id)
            relation_key = (source["page_id"], target_id, "reference")
            if relation_key in relation_keys:
                continue
            relation_keys.add(relation_key)
            relations.append(
                PageRelation(
                    generation=candidate,
                    from_page_id=source["page_id"],
                    to_page_id=target_id,
                    relation_type="reference",
                    weight=1.0,
                )
            )

    candidate.relations.all().delete()
    PageRelation.objects.bulk_create(relations, batch_size=500)
    return {
        "generation_id": candidate.pk,
        "relation_count": len(relations),
        "issues": issues,
    }


__all__ = ["GenerationRelationError", "rebuild_generation_relations"]
