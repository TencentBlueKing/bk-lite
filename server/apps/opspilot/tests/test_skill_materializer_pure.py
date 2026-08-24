"""SkillPackage → SKILL.md 物化器纯函数单元测试。

不依赖数据库 / 网络 / MinIO，全部使用普通 dict 输入与假后端桩。
"""
import pytest
import yaml

from apps.opspilot.services.skill_package.materializer import materialize_skill_package, render_skill_md, sanitize_skill_name

pytestmark = pytest.mark.unit


class FakeBackend:
    """记录所有 write / upload_files / chmod 调用的假后端。"""

    def __init__(self):
        self.writes = {}
        self.uploads = {}
        self.chmods = {}

    def write(self, file_path, content):
        self.writes[file_path] = content
        return {"file_path": file_path}

    def upload_files(self, files):
        for path, content in files:
            self.uploads[path] = content
            self.writes[path] = content

    def chmod(self, file_path, mode):
        self.chmods[file_path] = mode


def _split_frontmatter(skill_md):
    assert skill_md.startswith("---\n")
    _, fm, body = skill_md.split("---\n", 2)
    return yaml.safe_load(fm), body


# ---------------------------------------------------------------------------
# sanitize_skill_name
# ---------------------------------------------------------------------------


def test_sanitize_lowercases_and_hyphenates_spaces():
    assert sanitize_skill_name("My Cool Skill") == "my-cool-skill"


def test_sanitize_strips_invalid_and_collapses_hyphens():
    assert sanitize_skill_name("Foo__Bar  Baz!!!") == "foo-bar-baz"


def test_sanitize_unicode_becomes_hyphen_separated():
    # 中文等非 ascii 字符被替换为分隔符并最终清理
    assert sanitize_skill_name("巡检 report") == "report"


def test_sanitize_truncates_to_64_chars():
    name = sanitize_skill_name("a" * 200)
    assert len(name) <= 64
    assert name == "a" * 64


def test_sanitize_truncation_does_not_leave_trailing_hyphen():
    raw = "ab-" * 30  # 长度超过 64，第 64 位可能落在 '-' 上
    out = sanitize_skill_name(raw)
    assert len(out) <= 64
    assert not out.endswith("-")
    assert not out.startswith("-")


def test_sanitize_empty_falls_back():
    assert sanitize_skill_name("") == "skill"
    assert sanitize_skill_name("!!!") == "skill"


# ---------------------------------------------------------------------------
# render_skill_md
# ---------------------------------------------------------------------------


def test_render_produces_valid_frontmatter_and_body():
    pkg = {
        "package_id": "Network-Inspect",
        "name": "网络巡检",
        "description": "对网络设备做巡检",
        "skill_markdown": "# 巡检步骤\n1. 收集数据\n2. 输出报告",
    }
    md = render_skill_md(pkg)
    meta, body = _split_frontmatter(md)
    assert meta["name"] == "network-inspect"
    assert isinstance(meta["description"], str)
    assert "对网络设备做巡检" in meta["description"]
    assert "# 巡检步骤" in body
    assert body.strip().endswith("输出报告")


def test_render_name_max_64():
    pkg = {"package_id": "x" * 100, "skill_markdown": "body"}
    meta, _ = _split_frontmatter(render_skill_md(pkg))
    assert len(meta["name"]) <= 64


def test_render_description_truncated_to_1024():
    pkg = {
        "package_id": "p",
        "description": "长" * 5000,
        "skill_markdown": "body",
    }
    meta, _ = _split_frontmatter(render_skill_md(pkg))
    assert len(meta["description"]) <= 1024


def test_render_description_prefers_manifest_description():
    pkg = {
        "package_id": "p",
        "description": "fallback desc",
        "manifest": {"description": "manifest desc"},
        "skill_markdown": "body",
    }
    meta, _ = _split_frontmatter(render_skill_md(pkg))
    assert "manifest desc" in meta["description"]


def test_render_description_includes_triggers():
    pkg = {
        "package_id": "p",
        "description": "do a thing",
        "triggers": ["巡检", "inspect"],
        "skill_markdown": "body",
    }
    meta, _ = _split_frontmatter(render_skill_md(pkg))
    assert "巡检" in meta["description"]
    assert "inspect" in meta["description"]


def test_render_accepts_object_like_package():
    class Obj:
        package_id = "Obj-Skill"
        name = "对象技能"
        description = "desc"
        manifest = {}
        triggers = []
        skill_markdown = "# body"

    meta, body = _split_frontmatter(render_skill_md(Obj()))
    assert meta["name"] == "obj-skill"
    assert "# body" in body


def test_render_frontmatter_round_trips_through_yaml():
    # description 内含冒号、换行等特殊字符也应产生合法 YAML
    pkg = {
        "package_id": "tricky",
        "description": "key: value\nsecond line: yes",
        "skill_markdown": "body",
    }
    md = render_skill_md(pkg)
    meta, _ = _split_frontmatter(md)  # 不抛异常即合法
    assert meta["name"] == "tricky"


# ---------------------------------------------------------------------------
# materialize_skill_package
# ---------------------------------------------------------------------------


def test_materialize_writes_skill_md_to_expected_path():
    backend = FakeBackend()
    pkg = {"package_id": "Net Inspect", "skill_markdown": "# body"}
    written = materialize_skill_package(pkg, backend)
    assert "/skills/net-inspect/SKILL.md" in backend.writes
    assert "/skills/net-inspect/SKILL.md" in written
    assert backend.writes["/skills/net-inspect/SKILL.md"].startswith("---\n")


def test_materialize_honors_custom_skills_root():
    # 当后端用真实主机路径时（LocalShellBackend virtual_mode=False），
    # 必须把技能落到工作目录下的 skills_root，而非主机根 /skills。
    backend = FakeBackend()
    pkg = {"package_id": "Net Inspect", "skill_markdown": "# body"}
    written = materialize_skill_package(pkg, backend, skills_root="/work/u1/skills")
    assert "/work/u1/skills/net-inspect/SKILL.md" in backend.writes
    assert "/work/u1/skills/net-inspect/SKILL.md" in written
    assert not any(p.startswith("/skills/") for p in backend.writes)


def test_materialize_copies_scripts_references_assets():
    backend = FakeBackend()
    pkg = {
        "package_id": "demo",
        "skill_markdown": "# body",
        "scripts": {"run.py": "print(1)"},
        "references": {"guide.md": "ref"},
        "assets": {"logo.png": "binarydata"},
    }
    materialize_skill_package(pkg, backend)
    assert backend.writes["/skills/demo/scripts/run.py"] == "print(1)"
    assert backend.writes["/skills/demo/references/guide.md"] == "ref"
    assert backend.writes["/skills/demo/assets/logo.png"] == "binarydata"


def test_materialize_handles_nested_relative_paths():
    backend = FakeBackend()
    pkg = {
        "package_id": "demo",
        "skill_markdown": "# body",
        "scripts": {"sub/dir/run.py": "code"},
    }
    materialize_skill_package(pkg, backend)
    assert backend.writes["/skills/demo/scripts/sub/dir/run.py"] == "code"


def test_materialize_ignores_unsafe_relative_paths():
    backend = FakeBackend()
    pkg = {
        "package_id": "demo",
        "skill_markdown": "# body",
        "scripts": {"../escape.py": "evil", "/abs.py": "evil2"},
    }
    materialize_skill_package(pkg, backend)
    for path in backend.writes:
        assert "escape.py" not in path
        assert "/skills/demo/scripts//" not in path


def test_materialize_returns_all_written_paths():
    backend = FakeBackend()
    pkg = {
        "package_id": "demo",
        "skill_markdown": "# body",
        "scripts": {"run.py": "code"},
    }
    written = materialize_skill_package(pkg, backend)
    assert set(written) == set(backend.writes.keys())


def test_materialize_streaming_copies_bin_and_keeps_skill_md_rendered(tmp_path):
    extracted = tmp_path / "extracted"
    (extracted / "bin").mkdir(parents=True)
    (extracted / "scripts").mkdir()
    (extracted / "SKILL.md").write_text("# raw extracted, should not be copied\n", encoding="utf-8")
    (extracted / "skill.yaml").write_text("id: demo\n", encoding="utf-8")
    (extracted / "bin" / "tool.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    (extracted / "scripts" / "run.py").write_text("print(1)\n", encoding="utf-8")

    backend = FakeBackend()
    pkg = {
        "package_id": "demo",
        "skill_markdown": "# rendered body",
        "extracted_root": extracted,
    }
    materialize_skill_package(pkg, backend)

    skill_md = backend.writes["/skills/demo/SKILL.md"]
    assert skill_md.startswith("---\n")
    assert "# rendered body" in skill_md
    assert "raw extracted" not in skill_md
    assert "/skills/demo/skill.yaml" not in backend.writes
    assert backend.writes["/skills/demo/bin/tool.sh"] == "#!/bin/sh\necho hi\n"
    assert backend.writes["/skills/demo/scripts/run.py"] == "print(1)\n"


def test_materialize_streaming_uploads_binary_bytes(tmp_path):
    extracted = tmp_path / "extracted"
    (extracted / "assets").mkdir(parents=True)
    payload = bytes(range(256))
    (extracted / "assets" / "blob.bin").write_bytes(payload)

    backend = FakeBackend()
    materialize_skill_package(
        {"package_id": "demo", "skill_markdown": "# body", "extracted_root": extracted},
        backend,
    )
    assert backend.uploads["/skills/demo/assets/blob.bin"] == payload
    assert backend.writes["/skills/demo/assets/blob.bin"] == payload


def test_materialize_preserves_executable_bit(tmp_path, monkeypatch):
    extracted = tmp_path / "extracted"
    (extracted / "bin").mkdir(parents=True)
    script = extracted / "bin" / "run.sh"
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")

    monkeypatch.setattr(
        "apps.opspilot.services.skill_package.materializer._is_executable",
        lambda path: path.name == "run.sh",
    )
    backend = FakeBackend()
    materialize_skill_package(
        {"package_id": "demo", "skill_markdown": "# body", "extracted_root": extracted},
        backend,
    )
    assert backend.chmods["/skills/demo/bin/run.sh"] == 0o755
