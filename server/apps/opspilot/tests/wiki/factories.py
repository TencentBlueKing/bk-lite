from uuid import uuid4

from apps.opspilot.models import KnowledgePage, Material, WikiKnowledgeBase
from apps.opspilot.services.wiki.page_service import create_manual_page


def _unique_name(prefix):
    return f"{prefix}-{uuid4().hex}"


class WikiFactory:
    def knowledge_base(self, **overrides):
        values = {
            "name": _unique_name("wiki-kb"),
            "team": [1],
            "purpose_md": "# Purpose",
            "schema_md": "# Schema",
        }
        values.update(overrides)
        return WikiKnowledgeBase.objects.create(**values)

    def material(self, *, knowledge_base, **overrides):
        values = {
            "knowledge_base": knowledge_base,
            "name": _unique_name("wiki-material"),
            "material_type": "text",
            "text_content": "facts",
        }
        values.update(overrides)
        return Material.objects.create(**values)

    def page(self, *, knowledge_base, body="", **overrides):
        forbidden_fields = {"current_version", "current_version_id"} & overrides.keys()
        if forbidden_fields:
            fields = ", ".join(sorted(forbidden_fields))
            raise ValueError(f"WikiFactory.page forbids current_version override: {fields}")

        state_overrides = {field: overrides.pop(field) for field in ("contribution", "status", "update_method") if field in overrides}
        service_values = {
            "knowledge_base": knowledge_base,
            "page_type": overrides.pop("page_type", "concept"),
            "title": overrides.pop("title", _unique_name("wiki-page")),
            "body": body,
            "tags": overrides.pop("tags", None),
            "created_by": overrides.pop("created_by", ""),
        }
        if overrides:
            fields = ", ".join(sorted(overrides))
            raise TypeError(f"Unsupported WikiFactory.page fields: {fields}")

        page = create_manual_page(**service_values)
        if state_overrides:
            for field, value in state_overrides.items():
                setattr(page, field, value)
            page.save(update_fields=[*state_overrides, "updated_at"])
        return page


def create_unsafe_legacy_page_without_version(*, knowledge_base, **overrides):
    forbidden_fields = {"current_version", "current_version_id"} & overrides.keys()
    if forbidden_fields:
        fields = ", ".join(sorted(forbidden_fields))
        raise ValueError(f"Unsafe legacy helper must remain versionless: {fields}")

    values = {
        "knowledge_base": knowledge_base,
        "page_type": "concept",
        "title": _unique_name("unsafe-legacy-page"),
        "contribution": "ai",
    }
    values.update(overrides)
    return KnowledgePage.objects.create(**values)
