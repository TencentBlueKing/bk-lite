"""解析正文嵌入图片落盘与展示 URL 改写。"""

from __future__ import annotations

import base64
import hashlib
from types import SimpleNamespace
from urllib.parse import unquote

from apps.opspilot.services.wiki import parsed_media_service


def _patch_proxy_secret(monkeypatch):
    monkeypatch.setattr(
        parsed_media_service,
        "_media_proxy_secret",
        lambda: b"test-secret",
    )


def _assert_proxy_display(url: str, locator: str):
    assert url.startswith("/api/proxy/opspilot/wiki_mgmt/media/?")
    assert "sig=" in url
    assert locator in unquote(url)


def test_persist_embedded_images_uploads_and_rewrites(monkeypatch):
    saved = {}

    class Storage:
        def exists(self, path):
            return path in saved

        def save(self, path, content):
            saved[path] = content.read()
            return path

        def url(self, path):
            return f"https://minio.example/{path}?sig=1"

        def delete(self, path):
            saved.pop(path, None)

        def listdir(self, bucket):
            return [(name, None) for name in saved]

        @property
        def bucket(self):
            return "munchkin-private"

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    _patch_proxy_secret(monkeypatch)
    material = SimpleNamespace(id=9, knowledge_base_id=7)
    png = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"
    b64 = base64.b64encode(png).decode("ascii")
    md = f"# Slide\n\n![blue box](data:image/png;base64,{b64})\n\ntext"
    out = parsed_media_service.persist_embedded_images(material, md)
    digest = hashlib.sha256(png).hexdigest()
    locator = f"wiki/media/7/9/{digest}.png"
    assert locator in saved
    assert saved[locator] == png
    assert f"![blue box]({locator})" in out
    assert "data:image/png" not in out

    display = parsed_media_service.rewrite_media_urls_for_display(out)
    assert "![blue box](" in display
    assert locator in unquote(display)
    assert "/api/proxy/opspilot/wiki_mgmt/media/" in display
    assert "https://minio.example/" not in display


def test_rewrite_media_urls_handles_long_alt_and_dead_placeholders(monkeypatch):
    class Storage:
        def url(self, path):
            return f"https://cdn/{path}"

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    _patch_proxy_secret(monkeypatch)
    long_alt = "A" * 1200
    sha = "a" * 64
    locator = f"wiki/media/1/2/{sha}.png"
    md = f"![{long_alt}]({locator})\n\n" f"![architecture](Picture4.jpg)\n\n" f"keep https ![x](https://example.com/a.png)"
    out = parsed_media_service.rewrite_media_urls_for_display(md)
    assert "/api/proxy/opspilot/wiki_mgmt/media/" in out
    assert locator in unquote(out)
    assert "Picture4.jpg" not in out
    assert "图片：architecture" in out
    assert "https://example.com/a.png" in out


def test_persist_embedded_images_skips_when_no_data_uri():
    md = "![x](Picture1.jpg)\nplain"
    assert parsed_media_service.persist_embedded_images(SimpleNamespace(id=1, knowledge_base_id=1), md) == md


def test_rewrite_rejects_unsafe_locator(monkeypatch):
    class Storage:
        def url(self, path):
            raise AssertionError("unsafe locator should not call url")

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    md = "![x](wiki/media/1/2/../evil.png)"
    assert parsed_media_service.rewrite_media_urls_for_display(md) == md


def test_rewrite_mixed_signed_and_bare_locators(monkeypatch):
    """正文同时有 MinIO 签名 URL 与裸 wiki/media 时，二者都应变成同源代理 URL。"""

    class Storage:
        def url(self, path):
            return f"https://minio.example/{path}?sig=fresh"

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    _patch_proxy_secret(monkeypatch)
    sha_ok = "e" * 64
    sha_bad = "6" * 64
    loc_ok = f"wiki/media/3/5/{sha_ok}.png"
    loc_bad = f"wiki/media/3/5/{sha_bad}.png"
    stale = f"http://10.10.41.149:9000/munchkin-private/{loc_ok}?Signature=old"
    md = f'<p><img src="{stale}" alt="ok"></p>\n' f'<p><img src="{loc_bad}" alt="bad"></p>\n' f"![]({loc_bad})"
    out = parsed_media_service.rewrite_media_urls_for_display(md)
    assert "/api/proxy/opspilot/wiki_mgmt/media/" in out
    assert loc_ok in unquote(out) and loc_bad in unquote(out)
    assert "Signature=old" not in out
    assert "munchkin-private/https://" not in out
    assert f'src="{loc_bad}"' not in out
    assert "10.10.41.149" not in out


def test_rewrite_preserves_markdown_image_closing_paren(monkeypatch):
    class Storage:
        def url(self, path):
            return f"https://cdn/{path}?sig=1"

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    _patch_proxy_secret(monkeypatch)
    sha = "c" * 64
    locator = f"wiki/media/3/5/{sha}.png"
    stale = f"http://10.10.41.149:9000/munchkin-private/{locator}?Signature=old"
    out = parsed_media_service.rewrite_media_urls_for_display(f"![cover]({stale})")
    assert out.startswith("![cover](/api/proxy/opspilot/wiki_mgmt/media/?")
    assert out.endswith(")")
    assert locator in unquote(out)


def test_signed_media_url_prefers_proxy(monkeypatch):
    class Storage:
        def url(self, path):
            return f"https://cdn/{path}?sig=1"

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    monkeypatch.setattr(
        parsed_media_service,
        "_try_minio_presign",
        lambda locator: f"http://10.10.41.149:9000/munchkin-private/{locator}?X-Amz-Signature=x",
    )
    _patch_proxy_secret(monkeypatch)
    sha = "d" * 64
    locator = f"wiki/media/3/5/{sha}.png"
    url = parsed_media_service._signed_media_url(locator)
    _assert_proxy_display(url, locator)
    assert "10.10.41.149" not in url


def test_rewrite_html_img_bare_locator(monkeypatch):
    class Storage:
        def url(self, path):
            return f"https://cdn/{path}"

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    _patch_proxy_secret(monkeypatch)
    sha = "a" * 64
    locator = f"wiki/media/3/5/{sha}.png"
    md = f'<p><img src="{locator}" alt="cover"></p>'
    out = parsed_media_service.rewrite_media_urls_for_display(md)
    assert 'src="/api/proxy/opspilot/wiki_mgmt/media/?' in out
    assert f'src="{locator}"' not in out


def test_rewrite_leading_slash_locator(monkeypatch):
    class Storage:
        def url(self, path):
            return f"https://cdn/{path}"

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    _patch_proxy_secret(monkeypatch)
    sha = "b" * 64
    locator = f"wiki/media/3/5/{sha}.png"
    md = f"![x](/{locator})"
    out = parsed_media_service.rewrite_media_urls_for_display(md)
    assert out.startswith("![x](/api/proxy/opspilot/wiki_mgmt/media/?")
    assert f"](/{locator})" not in out


def test_delete_material_media_filters_prefix(monkeypatch):
    deleted = []

    class Storage:
        bucket = "munchkin-private"

        def listdir(self, bucket):
            return [
                ("wiki/media/7/9/aaaa.bin", None),
                ("wiki/media/7/8/bbbb.bin", None),
                ("wiki/parsed/7/9/x.md", None),
            ]

        def delete(self, path):
            deleted.append(path)

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    # sha 长度不足会被安全校验拒绝
    short = parsed_media_service.delete_material_media(7, 9)
    assert short["deleted"] == 0

    long_sha = "a" * 16

    class Storage2(Storage):
        def listdir(self, bucket):
            return [
                (f"wiki/media/7/9/{long_sha}.png", None),
                (f"wiki/media/7/8/{long_sha}.png", None),
            ]

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage2())
    result = parsed_media_service.delete_material_media(7, 9)
    assert result["deleted"] == 1
    assert deleted == [f"wiki/media/7/9/{long_sha}.png"]
