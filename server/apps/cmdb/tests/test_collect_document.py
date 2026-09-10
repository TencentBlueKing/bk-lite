from apps.cmdb.collect.extensions import CollectEnterpriseExtension
from apps.cmdb.services.collect_document import DOCUMENT_NOT_FOUND, get_collect_model_document


def _patch_extension(monkeypatch, *doc_dirs):
    monkeypatch.setattr(
        "apps.cmdb.services.collect_document.get_collect_enterprise_extension",
        lambda: CollectEnterpriseExtension(doc_dirs=doc_dirs),
    )


def test_enterprise_document_precedes_community_document(monkeypatch, settings, tmp_path):
    community_dir = tmp_path / "apps/cmdb/support-files/plugins_doc"
    enterprise_dir = tmp_path / "enterprise-docs"
    community_dir.mkdir(parents=True)
    enterprise_dir.mkdir()
    (community_dir / "same.md").write_text("community", encoding="utf-8")
    (enterprise_dir / "same.md").write_text("enterprise", encoding="utf-8")
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    _patch_extension(monkeypatch, enterprise_dir)

    assert get_collect_model_document("same") == "enterprise"


def test_document_falls_back_to_community(monkeypatch, settings, tmp_path):
    community_dir = tmp_path / "apps/cmdb/support-files/plugins_doc"
    community_dir.mkdir(parents=True)
    (community_dir / "mysql.md").write_text("community mysql", encoding="utf-8")
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    _patch_extension(monkeypatch, tmp_path / "missing-enterprise-docs")

    assert get_collect_model_document("mysql") == "community mysql"


def test_document_returns_stable_message_when_missing(monkeypatch, settings, tmp_path):
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    _patch_extension(monkeypatch)

    assert get_collect_model_document("missing") == DOCUMENT_NOT_FOUND


def test_document_path_does_not_escape_declared_root(monkeypatch, settings, tmp_path):
    document_dir = tmp_path / "docs"
    document_dir.mkdir()
    (tmp_path / "outside.md").write_text("outside", encoding="utf-8")
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    _patch_extension(monkeypatch, document_dir)

    assert get_collect_model_document("../outside") == DOCUMENT_NOT_FOUND


def test_english_document_preferred_over_default_markdown(monkeypatch, settings, tmp_path):
    community_dir = tmp_path / "apps/cmdb/support-files/plugins_doc"
    community_dir.mkdir(parents=True)
    (community_dir / "k8s_cluster.md").write_text("中文文档", encoding="utf-8")
    (community_dir / "k8s_cluster.en.md").write_text("English doc", encoding="utf-8")
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    _patch_extension(monkeypatch)

    assert get_collect_model_document("k8s_cluster", "en") == "English doc"
    assert get_collect_model_document("k8s_cluster", "zh-CN") == "中文文档"


def test_english_document_falls_back_to_default_markdown(monkeypatch, settings, tmp_path):
    community_dir = tmp_path / "apps/cmdb/support-files/plugins_doc"
    community_dir.mkdir(parents=True)
    (community_dir / "mysql.md").write_text("community mysql", encoding="utf-8")
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    _patch_extension(monkeypatch)

    assert get_collect_model_document("mysql", "en") == "community mysql"


def test_missing_document_uses_locale_message(monkeypatch, settings, tmp_path):
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    _patch_extension(monkeypatch)

    assert get_collect_model_document("missing", "en") == "Documentation not found."
    assert get_collect_model_document("missing", "zh-Hans") == DOCUMENT_NOT_FOUND


def test_community_plugin_docs_have_english_siblings():
    from pathlib import Path

    doc_dir = Path(__file__).resolve().parents[1] / "support-files" / "plugins_doc"
    missing = sorted(
        path.name for path in doc_dir.glob("*.md") if not path.name.endswith(".en.md") and not (doc_dir / f"{path.stem}.en.md").is_file()
    )
    assert missing == []
