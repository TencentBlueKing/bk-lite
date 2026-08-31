"""资料(Material)摄取:统一解析为 markdown + 生成 AI 摘要。"""

import hashlib
import os

from django.core.files.base import ContentFile
from django_minio_backend.models import MinioBackend
from openai import OpenAI

from apps.core.logger import opspilot_logger as logger
from apps.core.logger import safe_log_value
from apps.opspilot.models import MaterialVersion
from apps.opspilot.services.wiki.parsed_media_service import persist_embedded_images, rewrite_media_urls_for_display
from apps.opspilot.services.wiki.parsing import get_parser
from apps.opspilot.services.wiki.parsing.anthropic_vision_compat import build_anthropic_vision_client
from apps.opspilot.services.wiki.parsing.markitdown_parser import SUPPORTED_FILE_EXTENSIONS
from apps.opspilot.services.wiki.parsing.pdf_hybrid_parser import convert_pdf_hybrid, describe_page_with_vision

_PARSED_STORAGE = MinioBackend(bucket_name="munchkin-private")
_SUPPORTED_VISION_PROTOCOLS = frozenset({"openai", "anthropic"})


def _material_file_name(material):
    f = getattr(material, "file", None)
    return (getattr(f, "name", "") or getattr(material, "name", "") or "").strip()


def _file_extension(filename):
    return os.path.splitext(filename or "")[1].lower()


def _is_supported_file_extension(filename):
    extension = _file_extension(filename)
    return bool(extension) and extension in SUPPORTED_FILE_EXTENSIONS


def _supported_file_extensions_text():
    return ", ".join(SUPPORTED_FILE_EXTENSIONS)


def _read_file(material):
    """读取文件资料内容,返回 (文件名, bytes)。从 MinIO 读取;测试可 monkeypatch 本函数。

    file 资料未上传文件时返回 ("", b"")(由调用方按"无内容"处理为 failed,而非抛错)。
    """
    f = material.file
    if not f:
        return "", b""
    name = (getattr(f, "name", "") or material.name) or ""
    f.open("rb")
    try:
        data = f.read()
    finally:
        f.close()
    return name, data


def _vision_vendor_type(vision_model) -> str:
    vendor = getattr(vision_model, "vendor", None)
    return (getattr(vendor, "vendor_type", "") or "") if vendor is not None else ""


def _vision_log_flag(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "-"


def _vision_messages_have_image(messages) -> bool:
    for message in messages or []:
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"image_url", "image"}:
                return True
    return False


def _vision_response_stats(response):
    finish_reason = "-"
    content_chars = 0
    has_reasoning = False
    try:
        choice = (getattr(response, "choices", None) or [None])[0]
        if choice is None:
            return finish_reason, content_chars, has_reasoning
        finish_reason = str(getattr(choice, "finish_reason", "") or "-")
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if isinstance(content, str):
            content_chars = len(content.strip())
        if message is not None:
            for attr in ("reasoning_content", "reasoning"):
                raw = getattr(message, attr, None)
                if isinstance(raw, str) and raw.strip():
                    has_reasoning = True
                    break
    except (AttributeError, IndexError, TypeError):
        return "-", 0, False
    return finish_reason, content_chars, has_reasoning


class _LoggingVisionCompletions:
    def __init__(self, inner, *, material_id, model_name):
        self._inner = inner
        self._material_id = material_id
        self._model_name = model_name

    def create(self, *args, **kwargs):
        model = kwargs.get("model") or self._model_name
        has_image = _vision_messages_have_image(kwargs.get("messages"))
        max_tokens = kwargs.get("max_tokens")
        try:
            response = self._inner.create(*args, **kwargs)
        except Exception as exc:
            logger.warning(
                "wiki_vision_invoke material=%s model=%s has_image=%s max_tokens=%s " "status=error error_type=%s",
                self._material_id,
                safe_log_value(model or "-"),
                _vision_log_flag(has_image),
                max_tokens if max_tokens is not None else "-",
                type(exc).__name__,
            )
            raise
        finish_reason, content_chars, has_reasoning = _vision_response_stats(response)
        logger.info(
            "wiki_vision_invoke material=%s model=%s has_image=%s max_tokens=%s " "status=ok finish_reason=%s content_chars=%s has_reasoning=%s",
            self._material_id,
            safe_log_value(model or "-"),
            _vision_log_flag(has_image),
            max_tokens if max_tokens is not None else "-",
            finish_reason,
            content_chars,
            _vision_log_flag(has_reasoning),
        )
        return response


class _LoggingVisionChat:
    def __init__(self, completions):
        self.completions = completions


class _LoggingVisionClient:
    """Preserve OpenAI-shaped ``chat.completions.create`` while logging bounded stats."""

    def __init__(self, client, *, material_id, model_name):
        self._client = client
        self.chat = _LoggingVisionChat(
            _LoggingVisionCompletions(
                client.chat.completions,
                material_id=material_id,
                model_name=model_name,
            )
        )

    def __getattr__(self, name):
        return getattr(self._client, name)


def _wrap_vision_client(client, *, material_id, model_name):
    completions = getattr(getattr(client, "chat", None), "completions", None)
    if completions is None or not callable(getattr(completions, "create", None)):
        return client
    return _LoggingVisionClient(client, material_id=material_id, model_name=model_name)


def _vision_options(material):
    """Return MarkItDown vision options when image enhancement is explicitly enabled.

    OpenAI 协议直接用 OpenAI 客户端；Anthropic 协议用兼容适配器，对上
    MarkItDown / PDF 整页描述所需的 ``chat.completions.create`` 接口。
    """
    material_id = getattr(material, "id", None)
    if not getattr(material, "ocr_enhance", False):
        logger.info("wiki_vision_skip material=%s reason=ocr_enhance_off", material_id)
        return None, None
    vision_model = getattr(material.knowledge_base, "vision_model", None)
    if not vision_model:
        logger.info("wiki_vision_skip material=%s reason=no_vision_model", material_id)
        return None, None
    protocol = getattr(vision_model, "protocol_type", "openai") or "openai"
    if protocol not in _SUPPORTED_VISION_PROTOCOLS:
        logger.warning(
            "material %s vision_model=%s 协议=%s 不支持图片增强,跳过",
            material.id,
            vision_model.id,
            protocol,
        )
        return None, None
    try:
        if protocol == "anthropic":
            client = build_anthropic_vision_client(
                api_base=vision_model.openai_api_base,
                api_key=vision_model.openai_api_key,
                vendor_type=_vision_vendor_type(vision_model),
            )
        else:
            client = OpenAI(base_url=vision_model.openai_api_base, api_key=vision_model.openai_api_key)
    except Exception:
        logger.exception("material %s 图片增强客户端初始化失败 vision_model=%s", material.id, vision_model.id)
        return None, None
    model_name = vision_model.model_name
    logger.info(
        "wiki_vision_ready material=%s model=%s protocol=%s",
        material_id,
        safe_log_value(model_name or "-"),
        protocol,
    )
    return _wrap_vision_client(client, material_id=material_id, model_name=model_name), model_name


def _vision_parser_kwargs(vision_client, vision_model):
    kwargs = {"vision_client": vision_client}
    if vision_model:
        kwargs["vision_model"] = vision_model
    return kwargs


def _extract_file_markdown(material):
    name, data = _read_file(material)
    if not data:
        return ""
    if not _is_supported_file_extension(name):
        logger.info("material %s 文件格式暂不支持 filename=%s", material.id, name)
        return ""
    try:
        vision_client, vision_model = _vision_options(material)
        # PDF：按页 MarkItDown；碎表/转换失败页整页出图（需重新 ingest 才对存量生效）
        if _file_extension(name) == ".pdf":
            logger.info(
                "material %s PDF extract via hybrid filename=%s bytes=%s ocr_enhance=%s",
                material.id,
                name,
                len(data),
                bool(getattr(material, "ocr_enhance", False)),
            )
            describe_page = None
            if vision_client is not None and vision_model:

                def _describe_page(png_bytes, page_number, _client=vision_client, _model=vision_model):
                    return describe_page_with_vision(_client, _model, png_bytes, page_number)

                describe_page = _describe_page

            return convert_pdf_hybrid(
                material,
                data,
                vision_client=vision_client,
                vision_model=vision_model,
                describe_page=describe_page,
            )
        return get_parser().parse_file(data, name, **_vision_parser_kwargs(vision_client, vision_model))
    except Exception:
        logger.exception("material %s 文件解析失败", material.id)
        return ""


def _extract_web_markdown(material):
    if not material.url:
        return ""
    try:
        vision_client, vision_model = _vision_options(material)
        return get_parser().parse_url(material.url, **_vision_parser_kwargs(vision_client, vision_model))
    except Exception:
        logger.exception("material %s 网页解析失败 url=%s", material.id, material.url)
        return ""


def extract_text(material):
    """从 Material 提取 markdown 正文。

    返回提取到的文本;无法处理的类型/格式返回空串(由调用方决定状态)。
    """
    return extract_markdown(material)


def extract_markdown(material):
    if material.material_type == "text":
        try:
            return get_parser().parse_text(material.text_content or "")
        except Exception:
            logger.exception("material %s 文本解析失败", material.id)
            return ""
    if material.material_type == "file":
        return _extract_file_markdown(material)
    if material.material_type == "web":
        return _extract_web_markdown(material)
    logger.info("material %s type=%s 暂未支持解析", material.id, material.material_type)
    return ""


def compute_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def save_parsed_markdown(material, markdown, digest):
    path = f"wiki/parsed/{material.knowledge_base_id}/{material.id}/{digest}.md"
    return _PARSED_STORAGE.save(path, ContentFile((markdown or "").encode("utf-8")))


def _parsed_markdown_locator_parts(locator):
    parts = (locator or "").strip().replace("\\", "/").split("/")
    if len(parts) != 5:
        return None
    root, kind, knowledge_base_id, material_id, filename = parts
    if not (
        root == "wiki" and kind == "parsed" and knowledge_base_id.isdigit() and material_id.isdigit() and bool(filename) and filename.endswith(".md")
    ):
        return None
    return parts


def _is_safe_parsed_markdown_locator(locator):
    return _parsed_markdown_locator_parts(locator) is not None


def is_parsed_markdown_locator_for_material(locator, material_id):
    parts = _parsed_markdown_locator_parts(locator)
    if not parts:
        return False
    try:
        expected_material_id = int(material_id)
    except (TypeError, ValueError):
        return False
    return int(parts[3]) == expected_material_id


def delete_parsed_markdown(locator):
    locator = (locator or "").strip()
    if not _is_safe_parsed_markdown_locator(locator):
        return False
    try:
        _PARSED_STORAGE.delete(locator)
        return True
    except Exception:
        logger.exception("material 解析产物删除失败 locator=%s", locator)
        return False


def load_parsed_markdown(material, *, for_display=False):
    version = material.current_version or material.versions.order_by("-id").first()
    if not version or not version.content_locator:
        return ""
    try:
        with _PARSED_STORAGE.open(version.content_locator, "rb") as fp:
            data = fp.read()
    except Exception:
        logger.exception("material %s 解析产物读取失败", material.id)
        return ""
    if isinstance(data, bytes):
        text = data.decode("utf-8", errors="ignore")
    else:
        text = data or ""
    if for_display:
        return rewrite_media_urls_for_display(text)
    return text


def _llm_summarize(text, llm_model_id=None):
    """Return a deterministic ingest summary without spending LLM budget.

    Knowledge construction owns the per-material LLM budget and performs its
    bounded map/reduce there.  Ingest must not consume hidden calls before that
    budget exists.
    """

    del llm_model_id
    return str(text or "").strip()[:2000]


def _ingest_failure_reason(material):
    """text 为空时给出贴合实际的失败原因,区分:未上传文件 / 无法抽取 / 抓取失败 / 类型不支持。

    旧实现统一返回"暂不支持的资料类型解析: file",会把"文件没传上来"误报成"类型不支持",误导排查。
    """
    mt = material.material_type
    if mt == "file":
        if not material.file:
            return "文件资料未上传文件,无法解析"
        extension = _file_extension(_material_file_name(material))
        if not extension or extension not in SUPPORTED_FILE_EXTENSIONS:
            unsupported = extension or "无扩展名"
            return f"暂不支持的文件格式: {unsupported}; 支持格式: {_supported_file_extensions_text()}"
        return "未能从文件中解析出 markdown(文件可能为空、损坏、格式依赖缺失,或为需视觉增强的扫描件)"
    if mt == "web":
        if not material.url:
            return "网页资料缺少 URL,无法解析"
        return "未能抓取到网页正文(URL 不可达或页面无可提取内容)"
    if mt == "text":
        return "文本内容为空"
    return f"暂不支持的资料类型: {mt}"


def ingest_material(material, llm_model_id=None):
    """解析资料 + 生成摘要 + 更新状态。返回更新后的 material。"""
    logger.info(
        "material %s ingest start type=%s name=%s ocr_enhance=%s prev_hash=%s",
        material.id,
        getattr(material, "material_type", None),
        getattr(material, "name", None),
        bool(getattr(material, "ocr_enhance", False)),
        (getattr(material, "content_hash", None) or "")[:12],
    )
    markdown = extract_markdown(material)
    if not markdown:
        material.status = "parse_failed"
        material.error_message = _ingest_failure_reason(material)
        material.save(update_fields=["status", "error_message", "updated_at"])
        logger.warning(
            "material %s ingest parse_failed reason=%s",
            material.id,
            material.error_message,
        )
        return material
    # data URI → MinIO wiki/media，MD 引用稳定路径（对齐 llm_wiki 落盘图）
    markdown = persist_embedded_images(material, markdown)
    digest = compute_hash(markdown)
    if material.content_hash == digest:
        material.status = "done"
        material.error_message = ""
        material.save(update_fields=["status", "error_message", "updated_at"])
        logger.info(
            "material %s ingest unchanged hash=%s chars=%s (no new version)",
            material.id,
            digest[:12],
            len(markdown),
        )
        return material
    locator = save_parsed_markdown(material, markdown, digest)
    version = MaterialVersion.objects.create(material=material, content_locator=locator, content_hash=digest)
    material.current_version = version
    material.content_hash = digest
    material.ai_summary = _llm_summarize(markdown, llm_model_id)
    material.status = "done"
    material.error_message = ""
    material.save(update_fields=["current_version", "content_hash", "ai_summary", "status", "error_message", "updated_at"])
    logger.info(
        "material %s ingest done version=%s hash=%s chars=%s has_module_table=%s has_step_table=%s",
        material.id,
        version.id,
        digest[:12],
        len(markdown),
        "| 模块 | 功能 |" in markdown,
        "| 步骤 | 名称 | 说明 |" in markdown,
    )
    return material
