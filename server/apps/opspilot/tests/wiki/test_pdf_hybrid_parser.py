"""PDF hybrid parse: fragmented pages become wiki/media images."""

from types import SimpleNamespace

import fitz
import pytest

from apps.opspilot.services.wiki.parsing import pdf_hybrid_parser
from apps.opspilot.services.wiki.parsing.pdf_hybrid_parser import convert_pdf_hybrid

_FRAGMENTED = """
| ······ 负 | 网 防 存 | 机 主 | 基   |       |     |     |
| -------- | ----- | --- | --- | ----- | --- | --- |
| 载        | 络 火 储 | 房 机 | 础   | 自定义属性 | 发   | 变   |
| 均        | 设 墙   |     |     |       |     |     |
|          |       |     |     |       | 布   | 更   |
| 衡   | 备   |     |     |     |     |     |
| --- | --- | --- | --- | --- | --- | --- |
| 业   | 容 自 进 | 业 业 |     |     | 故   |     |
| --- | --- | --- | --- | --- | --- | --- |
| 务   | 器 定 程 | 务 务 | 业   |     | 维   |     |
"""

_NORMAL = """
# 正常页

| 组件 | 说明 | 功能 |
| --- | --- | --- |
| nginx | Web 服务器 | 反向代理 |
| mysql | 关系型数据库 | 持久化存储 |
| redis | 内存数据库 | 缓存与会话 |
"""

_FLOW_ZIGZAG = "\n".join(
    [
        "",
        "利用标准运维跨系统编排能力",
        "",
        (
            "|                   |        | 2. 版本文件上传      |          |             "
            "| 4. 停止进程        |                | 6. 进程启动        |                "
            "| 8. 告警屏蔽解除       |"
        ),
        (
            "| ----------------- | ------ | -------------- | -------- | ----------- "
            "| -------------- | -------------- | -------------- | -------------- "
            "| --------------- |"
        ),
        (
            "|                   |        | 通过作业平台把版本文件上传到 |          |             "
            "| 上机用命令行或脚本将进程临时 |                | 上机用命令行或脚本将服务进程 |                "
            "| 确认OK后，登录监控系统将之前 |"
        ),
        (
            "|                   |        |                | 发布平台的中转机 |             "
            "| 停止，为更新做准备      |                | 重新拉起，使其恢复服务    |                "
            "| 的屏蔽策略解除，恢复防护！   |"
        ),
        (
            "| 1. 版本打包           |        |                |          | 3. 屏蔽告警     "
            "|                | 5. 更新版本        |                | 7. 测试检查        "
            "|                 |"
        ),
        (
            "| 开发从git或svn将文件打包并交 |        |                |          | 前往监控系统屏蔽对应的 "
            "|                | 通过作业平台把版本文件分发到 |                | 利用自动化测试工具或系统跑一 "
            "|                 |"
        ),
        (
            "|                   | 付给运维人员 |                |          |             "
            "| 业务告警策略。        | 各个对应的服务主机上     |                | 遍测试流程，验证可用性    "
            "|                 |"
        ),
        "",
    ]
)


def _two_page_pdf_bytes() -> bytes:
    doc = fitz.open()
    for text in ("page-one", "page-two"):
        page = doc.new_page(width=300, height=200)
        page.insert_text((40, 80), text, fontsize=16)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def material():
    return SimpleNamespace(id=5, knowledge_base_id=3)


def test_convert_pdf_hybrid_rasterizes_fragmented_page(monkeypatch, material):
    pdf_bytes = _two_page_pdf_bytes()
    saved = []

    def fake_save(mat, data, content_type):
        assert mat is material
        assert content_type == "image/png"
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        path = f"wiki/media/{mat.knowledge_base_id}/{mat.id}/page{len(saved)}.png"
        saved.append(path)
        return path

    monkeypatch.setattr(pdf_hybrid_parser, "save_media_bytes", fake_save)

    responses = [_FRAGMENTED, _NORMAL]

    class FakeParser:
        def _convert(self, source, *, vision_client=None, vision_model=None):
            return responses.pop(0)

    out = convert_pdf_hybrid(material, pdf_bytes, parser=FakeParser())

    assert "<!-- Page number: 1 -->" in out
    assert "<!-- Page number: 2 -->" in out
    assert "![第 1 页](wiki/media/3/5/page0.png)" in out
    assert "nginx" in out
    assert "自定义属性" not in out  # fragmented table replaced
    assert len(saved) == 1


def test_convert_pdf_hybrid_normalizes_flow_table_without_rasterize(monkeypatch, material):
    pdf_bytes = _two_page_pdf_bytes()
    saved = []

    monkeypatch.setattr(
        pdf_hybrid_parser,
        "save_media_bytes",
        lambda *a, **k: saved.append("x") or "wiki/media/x.png",
    )

    responses = [_FLOW_ZIGZAG, _NORMAL]

    class FakeParser:
        def _convert(self, source, *, vision_client=None, vision_model=None):
            return responses.pop(0)

    out = convert_pdf_hybrid(material, pdf_bytes, parser=FakeParser())

    assert "| 步骤 | 名称 | 说明 |" in out
    assert "| 1 | 版本打包 |" in out
    assert "付给运维人员" in out
    assert "wiki/media/" not in out
    assert saved == []


def test_convert_pdf_hybrid_normalizes_architecture_without_rasterize(monkeypatch, material):
    pdf_bytes = _two_page_pdf_bytes()
    saved = []

    monkeypatch.setattr(
        pdf_hybrid_parser,
        "save_media_bytes",
        lambda mat, data, content_type: saved.append("ok") or f"wiki/media/{mat.knowledge_base_id}/{mat.id}/arch.png",
    )

    arch = """
# 节点管理产品架构

|                   | Agent管理 |         | 插件管理 |         |         |
| ----------------- | ------ | ------- | ---- | ------- | ------- |
| Agent状态管理         | Agent普通安装 | Agent批量安装 | 插件状态管理 | 插件安装维护 | 添加新插件包 |
| 云区域管理             |        |         |      |         |         |
| 云区域查看             |        |         |      |         | Proxy安装 |
| 云区域创建             |        |         |      |         |         |
| 任务历史              |        |         |      |         |         |
| 全局配置              |        |         |      |         |         |
| 查看历史任务            |        | 查看任务详情 |      |         |         |
|                   |        |         | GSE环境配置 |         | 任务配置 |
"""
    responses = [arch, _NORMAL]

    class FakeParser:
        def _convert(self, source, *, vision_client=None, vision_model=None):
            return responses.pop(0)

    out = convert_pdf_hybrid(material, pdf_bytes, parser=FakeParser())
    assert "| 模块 | 功能 |" in out
    assert "| Agent管理 |" in out
    assert "wiki/media/" not in out
    assert "nginx" in out
    assert saved == []


def test_convert_pdf_hybrid_salvages_when_rasterize_fails(monkeypatch, material):
    pdf_bytes = _two_page_pdf_bytes()

    def boom(*a, **k):
        raise RuntimeError("minio down")

    monkeypatch.setattr(pdf_hybrid_parser, "save_media_bytes", boom)

    # Char-split fragmented table: cannot normalize to architecture/flow table
    frag = """
| ······ 负 | 网 防 存 | 机 主 | 基   |       |     |     |
| -------- | ----- | --- | --- | ----- | --- | --- |
| 载        | 络 火 储 | 房 机 | 础   | 自定义属性 | 发   | 变   |
| 均        | 设 墙   |     |     |       |     |     |
|          |       |     |     |       | 布   | 更   |
| 衡   | 备   |     |     |     |     |     |
| --- | --- | --- | --- | --- | --- | --- |
| 业   | 容 自 进 | 业 业 |     |     | 故   |     |
"""

    class FakeParser:
        def _convert(self, source, *, vision_client=None, vision_model=None):
            return frag

    out = convert_pdf_hybrid(material, pdf_bytes, parser=FakeParser())
    # Rasterize failed → keep/salvage text rather than empty page
    assert "自定义属性" in out or "- " in out
    assert "wiki/media/" not in out


def test_convert_pdf_hybrid_rasterizes_when_markitdown_fails(monkeypatch, material):
    pdf_bytes = _two_page_pdf_bytes()
    saved = []

    monkeypatch.setattr(
        pdf_hybrid_parser,
        "save_media_bytes",
        lambda mat, data, content_type: saved.append("x") or f"wiki/media/{mat.knowledge_base_id}/{mat.id}/fail.png",
    )

    class BoomParser:
        def _convert(self, source, *, vision_client=None, vision_model=None):
            raise RuntimeError("markitdown down")

    out = convert_pdf_hybrid(material, pdf_bytes, parser=BoomParser())
    assert out.count("wiki/media/") == 2
    assert len(saved) == 2


def test_convert_pdf_hybrid_uses_vision_alt_when_provided(monkeypatch, material):
    pdf_bytes = _two_page_pdf_bytes()

    monkeypatch.setattr(
        pdf_hybrid_parser,
        "save_media_bytes",
        lambda mat, data, content_type: "wiki/media/3/5/abc.png",
    )

    class FragParser:
        def _convert(self, source, *, vision_client=None, vision_model=None):
            return _FRAGMENTED

    out = convert_pdf_hybrid(
        material,
        pdf_bytes,
        parser=FragParser(),
        describe_page=lambda png, n: f"页面概要{n}",
    )
    assert "![页面概要1](wiki/media/3/5/abc.png)" in out
    assert "![页面概要2](wiki/media/3/5/abc.png)" in out


def test_extract_file_markdown_routes_pdf_to_hybrid(monkeypatch):
    from apps.opspilot.services.wiki import material_service

    called = {}

    monkeypatch.setattr(
        material_service,
        "_read_file",
        lambda m: ("guide.pdf", b"%PDF-1.4 fake"),
    )
    monkeypatch.setattr(material_service, "_vision_options", lambda m: (None, None))

    def fake_hybrid(material, data, **kwargs):
        called["ok"] = True
        return "# hybrid\n"

    monkeypatch.setattr(material_service, "convert_pdf_hybrid", fake_hybrid)
    monkeypatch.setattr(
        material_service,
        "get_parser",
        lambda: (_ for _ in ()).throw(AssertionError("non-pdf path")),
    )

    mat = SimpleNamespace(
        id=1,
        knowledge_base_id=1,
        material_type="file",
        ocr_enhance=False,
        name="guide.pdf",
    )
    assert material_service._extract_file_markdown(mat) == "# hybrid\n"
    assert called.get("ok") is True


def test_extract_file_markdown_non_pdf_keeps_parser(monkeypatch):
    from apps.opspilot.services.wiki import material_service

    monkeypatch.setattr(
        material_service,
        "_read_file",
        lambda m: ("notes.docx", b"PK fake"),
    )
    monkeypatch.setattr(material_service, "_vision_options", lambda m: (None, None))
    monkeypatch.setattr(
        material_service,
        "convert_pdf_hybrid",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("pdf hybrid")),
    )

    class P:
        def parse_file(self, data, name, *, vision_client=None, vision_model=None):
            return "# docx body"

    monkeypatch.setattr(material_service, "get_parser", lambda: P())

    mat = SimpleNamespace(
        id=1,
        knowledge_base_id=1,
        material_type="file",
        ocr_enhance=False,
        name="notes.docx",
    )
    assert material_service._extract_file_markdown(mat) == "# docx body"
