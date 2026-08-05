"""解析正文中的嵌入图片：落盘到 MinIO，并在展示时改写为可访问 URL。

对齐 llm_wiki：图片作为资料资产持久化，Markdown 引用稳定路径
`wiki/media/<kb_id>/<material_id>/<sha>.<ext>`；私有桶在返回前端时再签发 URL。
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re

from django.core.files.base import ContentFile
from django_minio_backend.models import MinioBackend

logger = logging.getLogger("opspilot")

_MEDIA_STORAGE = MinioBackend(bucket_name="munchkin-private")

# ![alt](data:image/png;base64,...) — alt 不允许含 ]（MarkItDown 会去掉）
_DATA_URI_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\(data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)\)",
    re.IGNORECASE,
)

# 稳定 locator（可带 ./ 或 / 前缀；不依赖 alt，避免长描述漏改写）
_MEDIA_LOCATOR_RE = re.compile(
    r"(?:\.?/)?wiki/media/\d+/\d+/[a-f0-9]{16,}\.[a-z0-9]+",
    re.IGNORECASE,
)

# MarkItDown 未内嵌成功时残留的死链：![alt](Picture1.jpg)
# 排除 http(s)/data/wiki/media 与同源代理 /api/proxy/
_DEAD_LOCAL_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\((?!https?:|data:|wiki/media/|/api/proxy/)([^)\n]+)\)",
    re.IGNORECASE,
)

_CONTENT_TYPE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/tif": ".tif",
    "image/svg+xml": ".svg",
}


def media_prefix_for_material(knowledge_base_id, material_id) -> str:
    return f"wiki/media/{int(knowledge_base_id)}/{int(material_id)}/"


def _extension_for_content_type(content_type: str) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    return _CONTENT_TYPE_EXT.get(normalized, ".bin")


def _is_safe_media_locator(locator: str, *, knowledge_base_id=None, material_id=None) -> bool:
    parts = (locator or "").strip().replace("\\", "/").split("/")
    if len(parts) != 5:
        return False
    root, kind, kb, mid, filename = parts
    if root != "wiki" or kind != "media":
        return False
    if not (kb.isdigit() and mid.isdigit() and filename):
        return False
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    if knowledge_base_id is not None and int(kb) != int(knowledge_base_id):
        return False
    if material_id is not None and int(mid) != int(material_id):
        return False
    name, _, ext = filename.rpartition(".")
    if not name or not ext:
        return False
    if not re.fullmatch(r"[a-f0-9]{16,}", name.lower()):
        return False
    return True


def save_media_bytes(material, data: bytes, content_type: str) -> str:
    """写入图片字节，返回稳定 locator（同一内容幂等）。"""
    digest = hashlib.sha256(data).hexdigest()
    ext = _extension_for_content_type(content_type)
    path = f"{media_prefix_for_material(material.knowledge_base_id, material.id)}{digest}{ext}"
    if not _MEDIA_STORAGE.exists(path):
        _MEDIA_STORAGE.save(path, ContentFile(data))
    return path


def persist_embedded_images(material, markdown: str) -> str:
    """把 MarkItDown keep_data_uris 产出的 data URI 落盘，并改写为 wiki/media 路径。"""
    if not markdown or "data:image/" not in markdown.lower():
        return markdown or ""

    def replace(match: re.Match) -> str:
        alt = match.group(1) or ""
        content_type = match.group(2)
        b64 = re.sub(r"\s+", "", match.group(3) or "")
        try:
            raw = base64.b64decode(b64, validate=False)
        except Exception:
            logger.warning("material %s 图片 base64 解码失败，保留原 data URI", material.id)
            return match.group(0)
        if not raw:
            return match.group(0)
        try:
            locator = save_media_bytes(material, raw, content_type)
        except Exception:
            logger.exception("material %s 图片落盘失败", material.id)
            return match.group(0)
        safe_alt = re.sub(r"[\r\n\[\]]", " ", alt)
        safe_alt = re.sub(r"\s+", " ", safe_alt).strip()
        return f"![{safe_alt}]({locator})"

    return _DATA_URI_IMAGE_RE.sub(replace, markdown)


def _normalize_media_locator(raw: str) -> str:
    """去掉 ./ 或 / 前缀，得到可签发的稳定 locator。"""
    text = (raw or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("/"):
        text = text[1:]
    return text


def _try_minio_presign(locator: str) -> str | None:
    """直接走 minio client 预签名，避免 MinioBackend.url 的 bytes/expires 兼容问题。"""
    from datetime import timedelta

    try:
        storage = _MEDIA_STORAGE
        same_endpoints = getattr(storage, "same_endpoints", True)
        client = getattr(storage, "client", None)
        if not same_endpoints:
            client = getattr(storage, "client_external", None) or client
        if client is None or not hasattr(client, "presigned_get_object"):
            return None
        bucket = getattr(storage, "bucket", None)
        if not bucket:
            return None
        url = client.presigned_get_object(
            bucket_name=bucket,
            object_name=locator,
            expires=timedelta(days=7),
        )
    except Exception:
        logger.exception("wiki media 预签名失败 locator=%s", locator)
        return None
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        logger.error("wiki media 预签名非绝对 URL locator=%s url=%r", locator, url)
        return None
    return url


def _media_proxy_secret() -> bytes:
    from django.conf import settings

    raw = (getattr(settings, "SECRET_KEY", None) or "wiki-media-proxy").encode("utf-8")
    return raw


def build_media_proxy_url(locator: str, *, expires_in: int = 7 * 24 * 3600) -> str:
    """同源代理 URL（经 /api/proxy，img 无需 Bearer）。"""
    import hashlib
    import hmac
    import time
    from urllib.parse import quote

    locator = _normalize_media_locator(locator)
    exp = int(time.time()) + int(expires_in)
    payload = f"{locator}:{exp}".encode("utf-8")
    sig = hmac.new(_media_proxy_secret(), payload, hashlib.sha256).hexdigest()
    return "/api/proxy/opspilot/wiki_mgmt/media/" f"?locator={quote(locator, safe='')}" f"&exp={exp}&sig={sig}"


def verify_media_proxy_request(locator: str, exp: str | int | None, sig: str | None) -> bool:
    import hashlib
    import hmac
    import time

    locator = _normalize_media_locator(locator)
    if not _is_safe_media_locator(locator):
        return False
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_i < int(time.time()):
        return False
    expected = hmac.new(
        _media_proxy_secret(),
        f"{locator}:{exp_i}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return bool(sig) and hmac.compare_digest(expected, str(sig))


def open_media_bytes(locator: str):
    """打开 wiki/media 对象，返回 (fileobj, content_type)。"""
    locator = _normalize_media_locator(locator)
    if not _is_safe_media_locator(locator):
        raise FileNotFoundError(locator)
    ext = locator.rsplit(".", 1)[-1].lower()
    content_type = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "svg": "image/svg+xml",
        "tif": "image/tiff",
        "tiff": "image/tiff",
    }.get(ext, "application/octet-stream")
    return _MEDIA_STORAGE.open(locator, "rb"), content_type


def _is_displayable_media_url(url: str) -> bool:
    value = (url or "").strip()
    return value.startswith(("http://", "https://")) or value.startswith("/api/proxy/opspilot/wiki_mgmt/media/")


def _signed_media_url(locator: str) -> str:
    """返回可展示 URL；对合法 locator 绝不回退为裸 wiki/media。

    优先同源代理：浏览器往往无法直连 MinIO（私网 IP/防火墙），
    经 /api/proxy 由 Next→Django 拉流更可靠。
    """
    locator = _normalize_media_locator(locator)
    if not _is_safe_media_locator(locator):
        return locator
    proxy = build_media_proxy_url(locator)
    if _is_displayable_media_url(proxy):
        return proxy
    signed = _try_minio_presign(locator)
    if signed and _is_displayable_media_url(signed):
        return signed
    try:
        url = (_MEDIA_STORAGE.url(locator) or "").strip()
    except Exception:
        logger.exception("wiki media storage.url 失败 locator=%s", locator)
        url = ""
    if _is_displayable_media_url(url):
        return url
    logger.error("wiki media 无法生成可展示 URL locator=%s proxy=%r", locator, proxy)
    return proxy


def sign_media_locators(locators, *, knowledge_base_id=None, material_id=None) -> dict:
    """批量签发，返回 {locator: display_url}；非法项跳过。"""
    urls = {}
    for raw in locators or []:
        locator = _normalize_media_locator(str(raw or ""))
        if not locator:
            continue
        if not _is_safe_media_locator(
            locator,
            knowledge_base_id=knowledge_base_id,
            material_id=material_id,
        ):
            continue
        urls[locator] = _signed_media_url(locator)
    return urls


def _url_span_covering_locator(text: str, start: int, end: int) -> tuple[int, int]:
    """若 locator 已嵌在 http(s) URL 内，扩展为整段 URL（含 query）的起止。

    绝不能把 Markdown `![alt](url)` / `[text](url)` 的收尾 `)` 算进 URL，
    否则替换后会丢掉括号，图片语法裂成纯文本 + 自动链接。
    """
    prefix = text[max(0, start - 512) : start]
    matched = re.search(r"https?://[^\s\"'<>\])]*$", prefix, flags=re.IGNORECASE)
    if not matched:
        return start, end
    url_start = max(0, start - 512) + matched.start()
    url_end = end
    if url_end < len(text) and text[url_end] == "?":
        url_end += 1
        while url_end < len(text) and text[url_end] not in " \t\r\n\"'<>])":
            url_end += 1
    return url_start, url_end


def _replace_dead_local_image(match: re.Match) -> str:
    alt = (match.group(1) or "").strip()
    target = (match.group(2) or "").strip()
    # 已是可访问链接时不应进入此分支；双保险
    if target.startswith(("http://", "https://", "data:", "wiki/media/", "/wiki/media/", "/api/proxy/")):
        return match.group(0)
    if alt:
        return f"\n\n> 图片：{alt}\n\n"
    return "\n\n> （图片资源不可用）\n\n"


def _bare_media_locator_spans(text: str) -> list[tuple[int, int, str]]:
    """找出仍以裸路径出现的 wiki/media（不含已在 http(s) URL 内的）。"""
    spans: list[tuple[int, int, str]] = []
    for match in _MEDIA_LOCATOR_RE.finditer(text or ""):
        start, end = match.start(), match.end()
        url_start, _url_end = _url_span_covering_locator(text, start, end)
        if url_start < start:
            # 已包在绝对 URL 里
            continue
        spans.append((start, end, _normalize_media_locator(match.group(0))))
    return spans


def rewrite_media_urls_for_display(markdown: str) -> str:
    """展示前改写：wiki/media → 可加载 URL；保证全部 locator 都改写，禁止部分成功。

    覆盖形态：
    - 裸 locator：`wiki/media/...`、`/wiki/media/...`
    - HTML：`<img src="wiki/media/...">`
    - 已嵌入的 MinIO 预签名 URL（整段替换为新鲜签名，避免二次嵌套）
    """
    text = markdown or ""
    if "wiki/media/" not in text:
        if "![" in text:
            text = _DEAD_LOCAL_IMAGE_RE.sub(_replace_dead_local_image, text)
        return text

    locators = sorted(
        {_normalize_media_locator(m.group(0)) for m in _MEDIA_LOCATOR_RE.finditer(text)},
        key=len,
        reverse=True,
    )
    if not locators:
        idx = text.lower().index("wiki/media/")
        logger.error("wiki/media 存在但正则未匹配，样本=%r", text[idx : idx + 96])
    signed_map = {locator: _signed_media_url(locator) for locator in locators}
    # 合法 locator 必须得到可展示 URL
    for locator, signed in list(signed_map.items()):
        if _is_safe_media_locator(locator) and not _is_displayable_media_url(signed):
            signed_map[locator] = build_media_proxy_url(locator)

    for locator in locators:
        signed = signed_map[locator]
        if not _is_displayable_media_url(signed):
            continue
        # 1) 过期/旧预签名 URL → 新鲜可展示 URL
        text = re.sub(
            rf"https?://[^\s\"'<>\])]*{re.escape(locator)}[^\s\"'<>\])]*",
            signed,
            text,
            flags=re.IGNORECASE,
        )
        # 2) 裸 locator（不可嵌进已写入的绝对 URL / 代理 query）
        text = re.sub(
            rf"(?<![A-Za-z0-9\-._/:])(?:\./|/)?{re.escape(locator)}",
            signed,
            text,
        )

    # 3) 兜底：仍裸露的 locator 强制替换，确保「全部」成功
    for start, end, locator in reversed(_bare_media_locator_spans(text)):
        signed = signed_map.get(locator) or _signed_media_url(locator)
        if not _is_displayable_media_url(signed):
            signed = build_media_proxy_url(locator)
        text = text[:start] + signed + text[end:]

    leftover = _bare_media_locator_spans(text)
    if leftover:
        logger.error(
            "wiki media 改写后仍有裸路径 count=%s sample=%s",
            len(leftover),
            leftover[0][2],
        )

    if "![" in text:
        text = _DEAD_LOCAL_IMAGE_RE.sub(_replace_dead_local_image, text)
    return text


def delete_media_locator(locator: str) -> bool:
    locator = (locator or "").strip()
    if not _is_safe_media_locator(locator):
        return False
    try:
        _MEDIA_STORAGE.delete(locator)
        return True
    except Exception:
        logger.exception("wiki media 删除失败 locator=%s", locator)
        return False


def delete_material_media(knowledge_base_id, material_id) -> dict:
    """删除某资料下全部 wiki/media 对象。"""
    prefix = media_prefix_for_material(knowledge_base_id, material_id)
    return _delete_media_by_prefix(prefix)


def delete_knowledge_base_media(knowledge_base_id) -> dict:
    """删除某知识库下全部 wiki/media 对象。"""
    try:
        kb_id = int(knowledge_base_id)
    except (TypeError, ValueError):
        return {"prefix": "", "deleted": 0, "skipped": 0}
    if kb_id <= 0:
        return {"prefix": "", "deleted": 0, "skipped": 0}
    return _delete_media_by_prefix(f"wiki/media/{kb_id}/")


def _delete_media_by_prefix(prefix: str) -> dict:
    deleted = 0
    skipped = 0
    try:
        objects = _MEDIA_STORAGE.listdir(_MEDIA_STORAGE.bucket)
    except Exception:
        logger.exception("wiki media 目录扫描失败 prefix=%s", prefix)
        return {"prefix": prefix, "deleted": 0, "skipped": 0}

    for item in objects:
        object_name = item[0] if isinstance(item, tuple) else getattr(item, "object_name", "")
        object_name = (object_name or "").strip()
        if not object_name.startswith(prefix):
            continue
        if delete_media_locator(object_name):
            deleted += 1
        else:
            skipped += 1
    return {"prefix": prefix, "deleted": deleted, "skipped": skipped}
