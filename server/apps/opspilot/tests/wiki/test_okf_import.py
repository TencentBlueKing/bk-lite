import io
import zipfile
from copy import deepcopy

import pytest

from apps.opspilot.services.wiki.okf_import_service import (
    OkfParseError,
    classify_okf_image_target,
    collect_okf_image_refs,
    detect_bundle_root,
    disambiguate_okf_titles,
    inject_description,
    map_okf_page_type,
    page_media_locator,
    parse_okf_document,
    plan_okf_images,
    prepare_okf_documents,
    rewrite_okf_images,
    rewrite_okf_links,
    strip_bundle_root,
    validate_okf_image_bytes,
)


def test_parse_okf_document_reads_nested_yaml_and_comma_tags():
    text = "\n".join(
        [
            "---",
            "type: BigQuery Table",
            "title: Posts Answers",
            "description: Contains Stack Overflow answers, including their content, scores, and",
            "  associated metadata.",
            "tags: stackoverflow, answers, posts, Q&A",
            "generated:",
            "  by: reference_agent/gemini-2.5-flash",
            "  at: '2026-07-10T22:48:04+00:00'",
            "verified: { by: human:jsmith@acme, at: 2026-07-01T09:00:00Z }",
            "---",
            "",
            "See the [posts_questions](posts_questions.md) table.",
        ]
    )

    parsed = parse_okf_document("tables/posts_answers.md", text)

    assert parsed["okf_type"] == "BigQuery Table"
    assert parsed["title"] == "Posts Answers"
    assert parsed["tags"] == ["stackoverflow", "answers", "posts", "Q&A"]
    assert parsed["description"].startswith("Contains Stack Overflow answers")
    assert parsed["okf_frontmatter"]["generated"]["by"] == "reference_agent/gemini-2.5-flash"
    assert parsed["verified"][0]["by"] == "human:jsmith@acme"
    assert parsed["concept_id"] == "tables/posts_answers"


def test_parse_okf_document_rejects_missing_type_and_invalid_yaml():
    with pytest.raises(OkfParseError) as missing:
        parse_okf_document("readme.md", "# Hello\n")
    assert missing.value.reason == "yaml_invalid"

    with pytest.raises(OkfParseError) as no_type:
        parse_okf_document("notes.md", "---\ntitle: Notes\n---\n\nbody\n")
    assert no_type.value.reason == "type_missing"


def test_detect_bundle_root_drills_unique_top_directory():
    assert (
        detect_bundle_root(
            [
                "repo-main/tables/orders.md",
                "repo-main/index.md",
                "repo-main/attesters/sql.py",
            ]
        )
        == "repo-main"
    )
    assert detect_bundle_root(["tables/orders.md", "metrics/revenue.md"]) == ""
    assert detect_bundle_root(["readme.md"]) == ""


def test_strip_bundle_root_removes_github_prefix():
    assert strip_bundle_root("repo-main/tables/orders.md", "repo-main") == "tables/orders.md"
    assert strip_bundle_root("tables/orders.md", "") == "tables/orders.md"


def test_disambiguate_okf_titles_keeps_first_path_and_suffixes_later():
    result = disambiguate_okf_titles(
        [
            {"archive_path": "tables/revenue.md", "title": "Revenue"},
            {"archive_path": "metrics/revenue.md", "title": "Revenue"},
        ]
    )
    by_path = {item["archive_path"]: item for item in result}
    assert by_path["metrics/revenue.md"]["title"] == "Revenue"
    assert by_path["metrics/revenue.md"]["renamed_from"] == ""
    assert by_path["tables/revenue.md"]["title"] == "Revenue (tables)"
    assert by_path["tables/revenue.md"]["renamed_from"] == "Revenue"


def test_rewrite_okf_links_rewrites_bundle_paths_and_leaves_external_and_code():
    titles = {
        "tables/orders": "Customer Orders",
        "tables/posts_questions": "Posts Questions",
    }
    body = "\n".join(
        [
            "Join [orders](/tables/orders.md#schema) and [questions](posts_questions.md).",
            "See [docs](https://example.com) and [missing](/tables/missing.md).",
            "```markdown",
            "[orders](/tables/orders.md)",
            "```",
        ]
    )

    rewritten, stats = rewrite_okf_links(body, "tables/posts_answers.md", titles)

    assert "[[Customer Orders|orders]]" in rewritten
    assert "[[Posts Questions|questions]]" in rewritten
    assert "[docs](https://example.com)" in rewritten
    assert "[missing](/tables/missing.md)" in rewritten
    assert "```markdown\n[orders](/tables/orders.md)\n```" in rewritten.replace("\r\n", "\n")
    assert stats == {"rewritten": 2, "unresolved": 1}


def test_inject_description_skips_when_already_present():
    assert inject_description("body", "A metric.").startswith("> A metric.")
    original = "A metric. already here in the first characters of this body."
    assert inject_description(original, "A metric.") == original


def test_map_okf_page_type_matches_schema_case_insensitively():
    page_type, matched, extra = map_okf_page_type("metric", ["Metric", "concept"])
    assert (page_type, matched, extra) == ("Metric", True, [])
    page_type, matched, extra = map_okf_page_type("BigQuery Table", ["Metric", "concept"])
    assert page_type == "concept"
    assert matched is False
    assert extra == ["okf:BigQuery Table"]


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"payload"


def test_decode_zip_member_name_recovers_gbk_without_utf8_flag():
    from apps.opspilot.services.wiki.markdown_import_governance_service import decode_zip_member_name

    class GbkInfo:
        filename = "assets/s9-图片_2.jpg".encode("gbk").decode("cp437")
        flag_bits = 0

    assert decode_zip_member_name(GbkInfo()) == "assets/s9-图片_2.jpg"

    class Utf8Info:
        filename = "assets/s9-图片_2.jpg"
        flag_bits = 0x800

    assert decode_zip_member_name(Utf8Info()) == "assets/s9-图片_2.jpg"

    class AsciiInfo:
        filename = "assets/image2.jpg"
        flag_bits = 0

    assert decode_zip_member_name(AsciiInfo()) == "assets/image2.jpg"


def test_classify_okf_image_target_resolves_relative_and_encoded_paths():
    classified = classify_okf_image_target('../assets/x.png "t"', "guides/a.md")
    assert classified == {"reason": None, "target": "../assets/x.png", "image_path": "assets/x.png"}

    encoded = classify_okf_image_target("../assets/my%20shot.png#frag", "guides/a.md")
    assert encoded["image_path"] == "assets/my shot.png"

    rooted = classify_okf_image_target("/assets/x.png", "guides/a.md")
    assert rooted["image_path"] == "assets/x.png"

    assert classify_okf_image_target("https://cdn/x.png", "guides/a.md")["skip"] is True
    assert classify_okf_image_target("data:image/png;base64,abc", "guides/a.md")["skip"] is True
    assert classify_okf_image_target("wiki/media/1/pages/ab.png", "guides/a.md")["skip"] is True
    assert classify_okf_image_target("../assets/x.png?v=1", "guides/a.md")["reason"] == "invalid_query"
    assert classify_okf_image_target("../../../etc/x.png", "guides/a.md")["reason"] == "outside_bundle"


def test_collect_okf_image_refs_covers_inline_reference_fence_and_html():
    body = "\n".join(
        [
            '![a](../assets/x.png "t")',
            "![b][shot]",
            "[shot]: /assets/x.png",
            "```md",
            "![skip](../assets/x.png)",
            "```",
            '<img src="../assets/y.png">',
            "See [file](../assets/x.png)",
        ]
    )
    refs, html_unchecked = collect_okf_image_refs(body, "guides/a.md")
    paths = [item["image_path"] for item in refs]
    assert paths == ["assets/x.png", "assets/x.png"]
    assert html_unchecked == 1


def test_validate_okf_image_bytes_rejects_empty_fake_png_and_script_svg():
    assert validate_okf_image_bytes(PNG_BYTES, ".png") == (None, "image/png")
    assert validate_okf_image_bytes(b"", ".png")[0] == "not_image"
    assert validate_okf_image_bytes(b"not-a-png", ".png")[0] == "not_image"
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    assert validate_okf_image_bytes(svg, ".svg") == (None, "image/svg+xml")
    evil = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert validate_okf_image_bytes(evil, ".svg")[0] == "not_image"


def test_plan_okf_images_rewrites_and_dedupes_then_reports_missing():
    digest = __import__("hashlib").sha256(PNG_BYTES).hexdigest()
    locator = page_media_locator(7, digest, ".png")
    members = {"assets/x.png": PNG_BYTES}

    def read_member(path):
        return members.get(path)

    docs = [
        {"archive_path": "guides/a.md", "body": "![a](../assets/x.png)\n<img src='x.png'>\n"},
        {"archive_path": "guides/b.md", "body": "![same](/assets/x.png)\n"},
    ]
    rewritten, stats, uploads, missing = plan_okf_images(docs, knowledge_base_id=7, read_member=read_member)
    assert not missing
    assert stats == {"count": 1, "bytes": len(PNG_BYTES), "pages": 2, "html_unchecked": 1}
    assert uploads == [{"locator": locator, "relative": "assets/x.png", "content_type": "image/png"}]
    assert f"![a]({locator})" in rewritten[0]["body"]
    assert f"![same]({locator})" in rewritten[1]["body"]

    missing_docs = [{"archive_path": "guides/a.md", "body": "![a](../assets/gone.png)\n"}]
    _, _, _, missing = plan_okf_images(missing_docs, knowledge_base_id=7, read_member=read_member)
    assert missing[0]["reason"] == "not_found"
    assert missing[0]["archive_path"] == "guides/a.md"
    assert missing[0]["image_path"] == "assets/gone.png"

    rewritten_body = rewrite_okf_images("```\n![a](../assets/x.png)\n```\n", "guides/a.md", {"assets/x.png": locator})
    assert "![a](../assets/x.png)" in rewritten_body


def test_prepare_okf_documents_builds_meta_tags_and_rewrites():
    orders = parse_okf_document(
        "tables/orders.md",
        "\n".join(
            [
                "---",
                "type: entity",
                "title: Customer Orders",
                "---",
                "",
                "Order rows.",
            ]
        ),
    )
    metric = parse_okf_document(
        "metrics/revenue.md",
        "\n".join(
            [
                "---",
                "type: Metric",
                "title: Revenue",
                "description: Recognized revenue for a fiscal year.",
                "status: deprecated",
                "verified: { by: human:jsmith@acme, at: 2026-07-01T09:00:00Z }",
                "---",
                "",
                "# Definition",
                "",
                "Computed from [orders](/tables/orders.md).",
            ]
        ),
    )

    prepared, stats = prepare_okf_documents(
        [orders, metric],
        page_types=["entity", "concept"],
        okf_version="0.2",
    )
    by_path = {item["archive_path"]: item for item in prepared}
    revenue = by_path["metrics/revenue.md"]

    assert revenue["page_type"] == "concept"
    assert "okf:Metric" in revenue["tags"]
    assert "okf:human_reviewed" in revenue["tags"]
    assert "okf:deprecated" in revenue["tags"]
    assert revenue["body"].startswith("> Recognized revenue for a fiscal year.")
    assert "[[Customer Orders|orders]]" in revenue["body"]
    assert revenue["okf_meta"]["trust_tier"] == "human_reviewed"
    assert revenue["okf_meta"]["concept_id"] == "metrics/revenue"
    assert revenue["okf_meta"]["okf_version"] == "0.2"
    assert stats["links"]["rewritten"] == 1
    assert any(row["okf_type"] == "Metric" and row["matched"] is False for row in stats["type_mapping"])


def _zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return buffer.getvalue()


def _okf_zip(**pages):
    entries = {
        "index.md": '---\nokf_version: "0.2"\n---\n\n# Bundle\n',
        "log.md": "# Directory Update Log\n",
        "README.md": "This is not a concept.\n",
        "notes.md": "---\ntitle: Notes\n---\n\nMissing type.\n",
        "attesters/sql_equality.py": "print('skip')\n",
    }
    entries.update(pages)
    return _zip_bytes(entries)


@pytest.mark.django_db(transaction=True)
def test_okf_preflight_and_execute_import_bundle(wiki_factory):
    from apps.opspilot.models import KnowledgePage, PageRelation, WikiDirectory
    from apps.opspilot.services.wiki.markdown_import_governance_service import (
        MarkdownImportGovernanceError,
        execute_markdown_import,
        inspect_markdown_archive,
        preflight_markdown_import,
    )
    from apps.opspilot.services.wiki.structure_service import UNCLASSIFIED_DIRECTORY_KEY, bootstrap_knowledge_base

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()

    content = _okf_zip(
        **{
            "tables/orders.md": "\n".join(
                [
                    "---",
                    "type: entity",
                    "title: Customer Orders",
                    "tags: [sales]",
                    "---",
                    "",
                    "One row per order.",
                ]
            ),
            "metrics/revenue.md": "\n".join(
                [
                    "---",
                    "type: Metric",
                    "title: Revenue",
                    "description: Recognized revenue for a fiscal year.",
                    "verified: { by: human:jsmith@acme, at: 2026-07-01T09:00:00Z }",
                    "---",
                    "",
                    "Computed from [orders](/tables/orders.md) and [missing](./nope.md).",
                    "See [docs](https://example.com/policy).",
                ]
            ),
            "metrics/orders.md": "\n".join(
                [
                    "---",
                    "type: concept",
                    "title: Customer Orders",
                    "---",
                    "",
                    "Metric-side narrative.",
                ]
            ),
        }
    )
    wrapped = _zip_bytes(
        {
            "repo-main/index.md": '---\nokf_version: "0.2"\n---\n',
            "repo-main/tables/orders.md": "\n".join(
                [
                    "---",
                    "type: entity",
                    "title: Customer Orders",
                    "---",
                    "",
                    "Orders.",
                ]
            ),
            "repo-main/metrics/revenue.md": "\n".join(
                [
                    "---",
                    "type: Metric",
                    "title: Revenue",
                    "---",
                    "",
                    "See [orders](/tables/orders.md).",
                ]
            ),
        }
    )

    github_inspected = inspect_markdown_archive(wrapped, "bundle.zip", import_format="okf")
    assert github_inspected.archive_kind == "okf"
    assert github_inspected.bundle_root == "repo-main"
    assert {item["archive_path"] for item in github_inspected.documents} == {
        "tables/orders.md",
        "metrics/revenue.md",
    }

    third_party = inspect_markdown_archive(content, "plain.zip")
    assert third_party.archive_kind == "third_party"

    with pytest.raises(MarkdownImportGovernanceError) as restore_error:
        preflight_markdown_import(
            knowledge_base,
            content,
            filename="okf.zip",
            actor="admin",
            options={"import_format": "okf", "restore_structure": True},
        )
    assert restore_error.value.code == "native_structure_restore_unavailable"

    empty = _zip_bytes({"README.md": "no concepts", "script.py": "x"})
    with pytest.raises(MarkdownImportGovernanceError) as empty_error:
        inspect_markdown_archive(empty, "empty.zip", import_format="okf")
    assert empty_error.value.code == "okf_no_concepts"
    assert "type: concept" in str(empty_error.value)
    assert empty_error.value.details["skip_reason_counts"]

    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf", "create_directories_from_folders": True},
    )
    preview = preflight["preview"]
    assert preview["archive_kind"] == "okf"
    assert preview["okf"]["okf_version"] == "0.2"
    assert preview["okf"]["bundle_root"] == ""
    skipped_reasons = {item["reason"] for item in preview["okf"]["skipped"]}
    assert {"reserved", "yaml_invalid", "type_missing"} <= skipped_reasons
    assert preview["okf"]["links"]["rewritten"] >= 1
    assert preview["okf"]["links"]["unresolved"] >= 1
    by_path = {row["archive_path"]: row for row in preview["pages"]}
    assert by_path["metrics/orders.md"]["title"] == "Customer Orders"
    assert not by_path["metrics/orders.md"].get("renamed_from")
    assert by_path["tables/orders.md"]["title"] == "Customer Orders (tables)"
    assert by_path["tables/orders.md"]["renamed_from"] == "Customer Orders"
    assert any(row["okf_type"] == "Metric" and row["matched"] is False for row in preview["okf"]["type_mapping"])

    result = execute_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="okf.zip",
        actor="admin",
    )
    pages = {page.title: page for page in KnowledgePage.objects.filter(knowledge_base=knowledge_base)}
    assert pages["Revenue"].contribution == "ai"
    assert pages["Revenue"].page_type == "concept"
    assert "okf:Metric" in pages["Revenue"].tags
    assert "okf:human_reviewed" in pages["Revenue"].tags
    version = pages["Revenue"].current_version
    assert version.meta_snapshot["source"] == "okf_import"
    assert version.meta_snapshot["okf"]["trust_tier"] == "human_reviewed"
    assert version.meta_snapshot["okf"]["concept_id"] == "metrics/revenue"
    assert version.body.startswith("> Recognized revenue for a fiscal year.")
    assert "[[Customer Orders (tables)|orders]]" in version.body
    assert PageRelation.objects.filter(
        generation_id=result["generation_id"],
        from_page=pages["Revenue"],
        to_page=pages["Customer Orders (tables)"],
    ).exists()
    unclassified = WikiDirectory.objects.get(
        knowledge_base=knowledge_base,
        key=UNCLASSIFIED_DIRECTORY_KEY,
        status="active",
    )
    tables = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="tables", status="active")
    metrics = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="metrics", status="active")
    assert tables.parent_id == unclassified.pk
    assert metrics.parent_id == unclassified.pk

    knowledge_base.refresh_from_db()
    replay = preflight_markdown_import(
        knowledge_base,
        content,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf"},
    )
    replay_result = execute_markdown_import(
        knowledge_base,
        replay["token"],
        content,
        filename="okf.zip",
        actor="admin",
    )
    assert replay_result["counts"]["created"] == 0
    assert replay_result["counts"]["updated"] >= 1
    assert KnowledgePage.objects.filter(knowledge_base=knowledge_base).count() == 3


@pytest.mark.django_db(transaction=True)
def test_okf_reimport_of_human_page_creates_candidate(wiki_factory):
    from apps.opspilot.models import CheckItem
    from apps.opspilot.services.wiki.markdown_import_governance_service import execute_markdown_import, preflight_markdown_import
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    wiki_factory.page(
        knowledge_base=knowledge_base,
        title="Revenue",
        body="manual",
        contribution="human",
        page_type="concept",
    )
    content = _okf_zip(
        **{
            "metrics/revenue.md": "\n".join(
                [
                    "---",
                    "type: concept",
                    "title: Revenue",
                    "---",
                    "",
                    "Imported body.",
                ]
            )
        }
    )
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf"},
    )
    assert preflight["preview"]["pages"][0]["action"] == "candidate"
    result = execute_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="okf.zip",
        actor="admin",
    )
    assert result["counts"]["candidate"] == 1
    assert CheckItem.objects.filter(knowledge_base=knowledge_base, check_type="conflict").exists()


@pytest.mark.django_db(transaction=True)
def test_okf_maps_schema_page_type_and_falls_back_to_concept(wiki_factory):
    from apps.opspilot.models import KnowledgePage
    from apps.opspilot.services.wiki.markdown_import_governance_service import execute_markdown_import, preflight_markdown_import
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    revision = knowledge_base.active_structure_revision
    snapshot = dict(revision.structure_snapshot or {})
    snapshot["page_types"] = ["Metric", "concept"]
    revision.structure_snapshot = snapshot
    revision.save(update_fields=["structure_snapshot"])

    content = _okf_zip(
        **{
            "metrics/revenue.md": "\n".join(
                [
                    "---",
                    "type: metric",
                    "title: Revenue",
                    "---",
                    "",
                    "A metric.",
                ]
            ),
            "tables/customers.md": "\n".join(
                [
                    "---",
                    "type: BigQuery Table",
                    "title: Customers",
                    "---",
                    "",
                    "A table.",
                ]
            ),
        }
    )
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf"},
    )
    by_path = {row["archive_path"]: row for row in preflight["preview"]["pages"]}
    assert by_path["metrics/revenue.md"]["page_type"] == "Metric"
    assert by_path["tables/customers.md"]["page_type"] == "concept"
    mapping = {(row["okf_type"], row["page_type"], row["matched"]) for row in preflight["preview"]["okf"]["type_mapping"]}
    assert ("metric", "Metric", True) in mapping
    assert ("BigQuery Table", "concept", False) in mapping

    execute_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="okf.zip",
        actor="admin",
    )
    pages = {page.title: page for page in KnowledgePage.objects.filter(knowledge_base=knowledge_base)}
    assert pages["Revenue"].page_type == "Metric"
    assert "okf:metric" not in pages["Revenue"].tags
    assert pages["Customers"].page_type == "concept"
    assert "okf:BigQuery Table" in pages["Customers"].tags


def _add_root_directories(knowledge_base, names):
    from apps.opspilot.services.wiki.structure_service import get_structure, save_structure

    current = get_structure(knowledge_base)
    existing = [{"kind": "existing", **deepcopy(directory)} for directory in current["structure"]["directories"]]
    page_types = list(current["structure"]["page_types"] or ["concept"])
    save_structure(
        knowledge_base,
        {
            "structure_version": current["structure_revision"]["version"],
            "base_generation_id": current["active_generation"]["id"],
            "structure": {
                "format_version": 1,
                "page_types": page_types,
                "directories": [
                    *existing,
                    *[
                        {
                            "kind": "new",
                            "client_ref": f"okf-root-{name}",
                            "name": name,
                            "description": "",
                            "order": 50 + index,
                            "rules": {
                                "allowed_page_types": [],
                                "default_for_page_types": [],
                            },
                            "parent": None,
                        }
                        for index, name in enumerate(names)
                    ],
                ],
            },
        },
        operator="admin",
    )
    knowledge_base.refresh_from_db()


@pytest.mark.django_db(transaction=True)
def test_okf_import_places_pages_in_matching_structure_directories(wiki_factory):
    from apps.opspilot.models import KnowledgePage, WikiDirectory
    from apps.opspilot.services.wiki.markdown_import_governance_service import execute_markdown_import, preflight_markdown_import
    from apps.opspilot.services.wiki.structure_service import UNCLASSIFIED_DIRECTORY_KEY, bootstrap_knowledge_base

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    _add_root_directories(knowledge_base, ["tables", "operations"])

    content = _okf_zip(
        **{
            "tables/orders.md": "\n".join(
                [
                    "---",
                    "type: entity",
                    "title: Customer Orders",
                    "---",
                    "",
                    "Orders.",
                ]
            ),
            "operations/runbooks/upgrade.md": "\n".join(
                [
                    "---",
                    "type: concept",
                    "title: Upgrade Runbook",
                    "---",
                    "",
                    "Steps.",
                ]
            ),
            "wiki/operations/nested.md": "\n".join(
                [
                    "---",
                    "type: concept",
                    "title: Nested Should Not Hit Root",
                    "---",
                    "",
                    "Under wiki wrapper.",
                ]
            ),
        }
    )
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf", "create_directories_from_folders": True},
    )
    by_path = {row["archive_path"]: row for row in preflight["preview"]["pages"]}
    tables = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="tables", status="active")
    operations = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="operations", status="active")
    assert by_path["tables/orders.md"]["directory"]["directory_id"] == tables.pk
    assert by_path["operations/runbooks/upgrade.md"]["directory"]["pending_client_ref"]
    assert by_path["wiki/operations/nested.md"]["directory"]["pending_client_ref"]

    result = execute_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="okf.zip",
        actor="admin",
    )
    assert result["counts"]["created"] == 3
    pages = {page.title: page for page in KnowledgePage.objects.filter(knowledge_base=knowledge_base)}
    unclassified = WikiDirectory.objects.get(
        knowledge_base=knowledge_base,
        key=UNCLASSIFIED_DIRECTORY_KEY,
        status="active",
    )
    runbooks = WikiDirectory.objects.get(
        knowledge_base=knowledge_base,
        name="runbooks",
        parent_id=operations.pk,
        status="active",
    )
    wiki = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="wiki", status="active")
    nested_ops = WikiDirectory.objects.get(
        knowledge_base=knowledge_base,
        name="operations",
        parent_id=wiki.pk,
        status="active",
    )
    assert pages["Customer Orders"].directory_id == tables.pk
    assert pages["Upgrade Runbook"].directory_id == runbooks.pk
    assert pages["Nested Should Not Hit Root"].directory_id == nested_ops.pk
    assert wiki.parent_id == unclassified.pk
    assert not WikiDirectory.objects.filter(
        knowledge_base=knowledge_base,
        name="tables",
        parent_id=unclassified.pk,
        status="active",
    ).exists()


def _patch_page_media(monkeypatch):
    saved = {}

    class Storage:
        def exists(self, path):
            return path in saved

        def save(self, path, content):
            saved[path] = content.read() if hasattr(content, "read") else content
            return path

        def delete(self, path):
            saved.pop(path, None)

        def url(self, path):
            return f"https://cdn/{path}"

        def listdir(self, bucket):
            return [(name, None) for name in saved]

        @property
        def bucket(self):
            return "munchkin-private"

    from apps.opspilot.services.wiki import parsed_media_service

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    return saved


def _okf_page(title, body):
    return "\n".join(["---", "type: concept", f"title: {title}", "---", "", body, ""])


@pytest.mark.django_db(transaction=True)
def test_okf_preflight_rejects_missing_and_fake_images(wiki_factory, monkeypatch):
    from apps.opspilot.services.wiki.markdown_import_governance_service import (
        MarkdownImportGovernanceError,
        inspect_markdown_archive,
        preflight_markdown_import,
    )
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    _patch_page_media(monkeypatch)
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()

    missing_zip = _okf_zip(**{"guides/a.md": _okf_page("Guide A", "![a](../assets/gone.png)")})
    with pytest.raises(MarkdownImportGovernanceError) as missing:
        preflight_markdown_import(
            knowledge_base,
            missing_zip,
            filename="okf.zip",
            actor="admin",
            options={"import_format": "okf"},
        )
    assert missing.value.code == "okf_images_missing"
    assert missing.value.details["missing"][0]["reason"] == "not_found"
    assert missing.value.details["missing"][0]["archive_path"] == "guides/a.md"
    assert missing.value.details["missing"][0]["image_path"] == "assets/gone.png"

    escaped = _okf_zip(**{"guides/a.md": _okf_page("Guide A", "![a](../../../etc/x.png)")})
    with pytest.raises(MarkdownImportGovernanceError) as escaped_error:
        preflight_markdown_import(
            knowledge_base,
            escaped,
            filename="okf.zip",
            actor="admin",
            options={"import_format": "okf"},
        )
    assert escaped_error.value.details["missing"][0]["reason"] == "outside_bundle"

    queried = _okf_zip(
        **{
            "guides/a.md": _okf_page("Guide A", "![a](../assets/x.png?v=1)"),
            "assets/x.png": PNG_BYTES,
        }
    )
    with pytest.raises(MarkdownImportGovernanceError) as query_error:
        preflight_markdown_import(
            knowledge_base,
            queried,
            filename="okf.zip",
            actor="admin",
            options={"import_format": "okf"},
        )
    assert query_error.value.details["missing"][0]["reason"] == "invalid_query"

    fake = _okf_zip(
        **{
            "guides/a.md": _okf_page("Guide A", "![a](../assets/x.png)"),
            "assets/x.png": b"not-an-image",
        }
    )
    with pytest.raises(MarkdownImportGovernanceError) as fake_error:
        preflight_markdown_import(
            knowledge_base,
            fake,
            filename="okf.zip",
            actor="admin",
            options={"import_format": "okf"},
        )
    assert fake_error.value.details["missing"][0]["reason"] == "not_image"

    unused = _okf_zip(**{"guides/a.md": _okf_page("Guide A", "No images.")})
    preflight = preflight_markdown_import(
        knowledge_base,
        unused,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf"},
    )
    assert preflight["preview"]["okf"]["images"]["count"] == 0
    inspected = inspect_markdown_archive(unused, "okf.zip", import_format="okf")
    assert inspected.okf_image_uploads == ()


@pytest.mark.django_db(transaction=True)
def test_okf_execute_persists_shared_image_and_gcs_unreferenced(wiki_factory, monkeypatch):
    from apps.opspilot.models import KnowledgePage
    from apps.opspilot.services.wiki.markdown_import_governance_service import execute_markdown_import, preflight_markdown_import
    from apps.opspilot.services.wiki.okf_import_service import page_media_locator
    from apps.opspilot.services.wiki.parsed_media_service import rewrite_media_urls_for_display
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    saved = _patch_page_media(monkeypatch)
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    locator = page_media_locator(knowledge_base.pk, __import__("hashlib").sha256(PNG_BYTES).hexdigest(), ".png")

    shared = _zip_bytes(
        {
            "index.md": '---\nokf_version: "0.2"\n---\n',
            "guides/a.md": _okf_page("Guide A", "![a](../assets/x.png)"),
            "guides/b.md": _okf_page("Guide B", "![b](/assets/x.png)"),
            "assets/x.png": PNG_BYTES,
        }
    )
    preflight = preflight_markdown_import(
        knowledge_base,
        shared,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf"},
    )
    assert preflight["preview"]["okf"]["images"]["count"] == 1
    assert preflight["preview"]["okf"]["images"]["pages"] == 2
    assert saved == {}

    execute_markdown_import(
        knowledge_base,
        preflight["token"],
        shared,
        filename="okf.zip",
        actor="admin",
    )
    assert locator in saved
    pages = {page.title: page for page in KnowledgePage.objects.filter(knowledge_base=knowledge_base)}
    assert f"![a]({locator})" in pages["Guide A"].current_version.body
    assert f"![b]({locator})" in pages["Guide B"].current_version.body
    from apps.opspilot.services.wiki import parsed_media_service as media_mod

    monkeypatch.setattr(media_mod, "_media_proxy_secret", lambda: b"test-secret")
    display = rewrite_media_urls_for_display(pages["Guide A"].current_version.body)
    assert "/api/proxy/opspilot/wiki_mgmt/media/" in display

    only_b = _zip_bytes(
        {
            "index.md": '---\nokf_version: "0.2"\n---\n',
            "guides/a.md": _okf_page("Guide A", "No picture now."),
            "guides/b.md": _okf_page("Guide B", "![b](/assets/x.png)"),
            "assets/x.png": PNG_BYTES,
        }
    )
    again = preflight_markdown_import(
        knowledge_base,
        only_b,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf"},
    )
    execute_markdown_import(knowledge_base, again["token"], only_b, filename="okf.zip", actor="admin")
    assert locator in saved

    none = _zip_bytes(
        {
            "index.md": '---\nokf_version: "0.2"\n---\n',
            "guides/a.md": _okf_page("Guide A", "No picture now."),
            "guides/b.md": _okf_page("Guide B", "Also none."),
        }
    )
    last = preflight_markdown_import(
        knowledge_base,
        none,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf"},
    )
    execute_markdown_import(knowledge_base, last["token"], none, filename="okf.zip", actor="admin")
    assert locator not in saved

    failing = _zip_bytes(
        {
            "index.md": '---\nokf_version: "0.2"\n---\n',
            "guides/c.md": _okf_page("Guide C", "![c](../assets/x.png)"),
            "assets/x.png": PNG_BYTES,
        }
    )
    from apps.opspilot.services.wiki import markdown_import_governance_service as gov

    def boom(*args, **kwargs):
        raise RuntimeError("minio-down")

    monkeypatch.setattr(gov, "save_page_media_bytes", boom)
    fail_preflight = preflight_markdown_import(
        knowledge_base,
        failing,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf"},
    )
    with pytest.raises(RuntimeError):
        execute_markdown_import(
            knowledge_base,
            fail_preflight["token"],
            failing,
            filename="okf.zip",
            actor="admin",
        )
    assert KnowledgePage.objects.filter(knowledge_base=knowledge_base, title="Guide C").count() == 0


@pytest.mark.django_db(transaction=True)
def test_third_party_markdown_zip_still_skips_images(wiki_factory):
    from apps.opspilot.services.wiki.markdown_import_governance_service import inspect_markdown_archive

    content = _zip_bytes(
        {
            "note.md": "# Hello\n\n![a](./x.png)\n",
            "x.png": PNG_BYTES,
        }
    )
    inspected = inspect_markdown_archive(content, "plain.zip")
    assert inspected.archive_kind == "third_party"
    assert inspected.documents[0]["body"].strip().endswith("![a](./x.png)")
    assert inspected.skipped_entries >= 1
