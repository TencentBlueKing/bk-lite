"""Generation-scoped Wiki relation helpers."""

import re

from apps.opspilot.services.wiki.active_generation_query_service import assert_read_scope_current, bind_read_scope, relation_queryset

LINK_RE = re.compile(r"\[\[\s*([^\]|\n]+?)(?:\|([^\]\n]*))?\s*\]\]")


def normalize_wikilink_key(value):
    """Normalize title/slug-style WikiLink targets for matching."""
    normalized = (value or "").strip().replace("\\", "/")
    leaf = normalized.rsplit("/", 1)[-1]
    if leaf.lower().endswith(".md"):
        leaf = leaf[:-3]
    return re.sub(r"[\s\-_]+", "", leaf.lower())


def list_relations(knowledge_base):
    """Return relation edges from the active generation only."""
    read_scope = bind_read_scope(knowledge_base)
    qs = relation_queryset(knowledge_base, read_scope=read_scope).select_related("from_page", "to_page")
    result = [
        {
            "from": relation.from_page_id,
            "from_title": relation.from_page.title,
            "to": relation.to_page_id,
            "to_title": relation.to_page.title,
            "relation_type": relation.relation_type,
            "weight": relation.weight,
        }
        for relation in qs
    ]
    assert_read_scope_current(read_scope)
    return result


def rebuild_generation_relations(candidate_id, *, pending_material_ids_by_page=None):
    """Materialize deterministic relations inside a staging generation."""
    from apps.opspilot.services.wiki.generation_relation_service import rebuild_generation_relations as rebuild

    return rebuild(
        candidate_id,
        pending_material_ids_by_page=pending_material_ids_by_page,
    )
