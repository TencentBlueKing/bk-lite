from pathlib import Path

import pytest


@pytest.mark.django_db
def test_factory_default_knowledge_base_and_material_names_do_not_collide():
    from apps.opspilot.tests.wiki.factories import WikiFactory

    factory = WikiFactory()
    first_kb = factory.knowledge_base()
    second_kb = factory.knowledge_base()
    first_material = factory.material(knowledge_base=first_kb)
    second_material = factory.material(knowledge_base=first_kb)

    assert first_kb.name != second_kb.name
    assert first_material.name != second_material.name


@pytest.mark.django_db
def test_factory_page_uses_real_domain_service_and_keeps_body_on_current_version():
    from apps.opspilot.tests.wiki.factories import WikiFactory

    factory = WikiFactory()
    knowledge_base = factory.knowledge_base()

    page = factory.page(knowledge_base=knowledge_base, title="domain page", body="domain body")

    assert page.current_version is not None
    assert page.current_version.body == "domain body"
    assert page.current_version.is_current is True
    assert page.current_version.change_type == "human_edit"
    assert page.page_versions.count() == 1
    assert page.contribution == "human"
    assert page.update_method == "human_edit"


@pytest.mark.django_db
def test_factory_page_allows_explicit_domain_state_overrides():
    from apps.opspilot.tests.wiki.factories import WikiFactory

    factory = WikiFactory()
    knowledge_base = factory.knowledge_base()

    page = factory.page(
        knowledge_base=knowledge_base,
        contribution="ai",
        status="archived",
        update_method="rebuild",
    )

    assert page.contribution == "ai"
    assert page.status == "archived"
    assert page.update_method == "rebuild"
    assert page.current_version is not None


@pytest.mark.django_db
def test_factory_page_rejects_current_version_override():
    from apps.opspilot.tests.wiki.factories import WikiFactory

    factory = WikiFactory()
    knowledge_base = factory.knowledge_base()

    with pytest.raises(ValueError, match="current_version"):
        factory.page(knowledge_base=knowledge_base, current_version=None)


@pytest.mark.django_db
def test_unsafe_legacy_helper_is_the_explicit_versionless_escape_hatch():
    from apps.opspilot.tests.wiki.factories import WikiFactory, create_unsafe_legacy_page_without_version

    knowledge_base = WikiFactory().knowledge_base()

    page = create_unsafe_legacy_page_without_version(knowledge_base=knowledge_base, title="legacy")

    assert page.current_version is None
    assert page.page_versions.count() == 0


def test_source_guard_ignores_comments_and_strings():
    from apps.opspilot.tests.wiki.source_guard import find_knowledge_page_creation_violations

    source = """
# KnowledgePage.objects.create(title='comment')
EXAMPLE = "KnowledgePage(title='string')"
"""

    assert find_knowledge_page_creation_violations(source) == []


@pytest.mark.parametrize(
    ("source", "expected_operation"),
    [
        ("KnowledgePage.objects.create(title='x')", "objects.create"),
        ("KnowledgePage.objects.get_or_create(title='x')", "objects.get_or_create"),
        ("KnowledgePage.objects.update_or_create(title='x')", "objects.update_or_create"),
        ("KnowledgePage.objects.bulk_create([])", "objects.bulk_create"),
        ("KnowledgePage(title='x')", "constructor"),
    ],
)
def test_source_guard_reports_real_orm_and_constructor_bypasses(source, expected_operation):
    from apps.opspilot.tests.wiki.source_guard import find_knowledge_page_creation_violations

    violations = find_knowledge_page_creation_violations(source, filename="planned_test.py")

    assert [violation.operation for violation in violations] == [expected_operation]
    assert violations[0].path == Path("planned_test.py")
    assert violations[0].line == 1


def test_source_guard_recognizes_only_planned_wiki_test_names():
    from apps.opspilot.tests.wiki.source_guard import is_planned_wiki_test_path

    planned_paths = [
        Path("test_directory_x.py"),
        Path("test_generation_x.py"),
        Path("test_structure_x.py"),
        Path("test_wiki_directory_views.py"),
    ]
    excluded_paths = [
        Path("test_existing_history.py"),
        Path("factories.py"),
    ]

    assert all(is_planned_wiki_test_path(path) for path in planned_paths)
    assert not any(is_planned_wiki_test_path(path) for path in excluded_paths)


def test_current_planned_wiki_tests_pass_source_guard():
    from apps.opspilot.tests.wiki.source_guard import scan_planned_wiki_tests

    assert scan_planned_wiki_tests(Path(__file__).parent) == []


@pytest.mark.django_db
def test_wiki_factory_fixture_is_available(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base(name="fixture-kb")

    assert knowledge_base.name == "fixture-kb"
