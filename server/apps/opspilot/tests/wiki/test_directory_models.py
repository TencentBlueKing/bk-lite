import pytest
from django.db import IntegrityError, connection, models, transaction
from django.db.models.deletion import ProtectedError

from apps.opspilot.models import WikiDirectory, WikiGenerationPage
from apps.opspilot.services.wiki.page_service import create_manual_page
from apps.opspilot.services.wiki.purpose_schema_service import FROZEN_ROOT_KEYS
from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

pytestmark = pytest.mark.django_db(transaction=True)


def _ready_kb(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    return knowledge_base


def test_directory_key_is_unique_per_knowledge_base_but_reusable_across_kbs(wiki_factory):
    first = _ready_kb(wiki_factory)
    second = _ready_kb(wiki_factory)

    first_keys = set(first.directories.values_list("key", flat=True))
    second_keys = set(second.directories.values_list("key", flat=True))
    assert first_keys == {"__unclassified__", *FROZEN_ROOT_KEYS}
    assert second_keys == first_keys
    assert first.directories.filter(key="__unclassified__").count() == 1
    assert second.directories.filter(key="__unclassified__").count() == 1
    with pytest.raises(IntegrityError), transaction.atomic():
        WikiDirectory.objects.create(
            knowledge_base=first,
            key="__unclassified__",
            name="重复目录",
        )


def test_generation_member_database_constraint_rejects_non_active_page_status(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    page = create_manual_page(
        knowledge_base,
        page_type="concept",
        title="成员状态约束",
        body="正文",
        created_by="admin",
    )
    knowledge_base.refresh_from_db()
    member = knowledge_base.active_generation.page_members.get(page=page)

    with pytest.raises(ValueError, match="逐条 save"):
        WikiGenerationPage.objects.filter(pk=member.pk).update(page_status="archived")
    if connection.features.supports_table_check_constraints:
        with pytest.raises(IntegrityError), transaction.atomic():
            models.QuerySet(model=WikiGenerationPage, using="default").filter(pk=member.pk).update(page_status="archived")


def test_generation_member_protects_retained_page_version(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    page = create_manual_page(
        knowledge_base,
        page_type="concept",
        title="历史版本保护",
        body="正文",
        created_by="admin",
    )
    retained_version = page.current_version

    with pytest.raises(ProtectedError):
        retained_version.delete()
