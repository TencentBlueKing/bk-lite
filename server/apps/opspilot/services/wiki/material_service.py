"""资料(Material)摄取:统一解析为 markdown + 生成 AI 摘要。"""

import hashlib
import logging
import os

from django.core.files.base import ContentFile
from django_minio_backend.models import MinioBackend
from openai import OpenAI

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import LLMModel, MaterialVersion
from apps.opspilot.services.wiki.parsing import get_parser
from apps.opspilot.services.wiki.parsing.markitdown_parser import SUPPORTED_FILE_EXTENSIONS
from apps.opspilot.services.wiki.text_utils import split_text_for_llm

logger = logging.getLogger("opspilot")

_PARSED_STORAGE = MinioBackend(bucket_name="munchkin-private")


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


def _vision_options(material):
    """Return MarkItDown vision options when image enhancement is explicitly enabled."""
    if not getattr(material, "ocr_enhance", False):
        return None, None
    vision_model = getattr(material.knowledge_base, "vision_model", None)
    if not vision_model:
        return None, None
    if getattr(vision_model, "protocol_type", "openai") != "openai":
        logger.warning("material %s vision_model=%s 非 OpenAI 兼容协议,跳过图片增强", material.id, vision_model.id)
        return None, None
    try:
        client = OpenAI(base_url=vision_model.openai_api_base, api_key=vision_model.openai_api_key)
    except Exception:
        logger.exception("material %s 图片增强客户端初始化失败 vision_model=%s", material.id, vision_model.id)
        return None, None
    return client, vision_model.model_name


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


def load_parsed_markdown(material):
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
        return data.decode("utf-8", errors="ignore")
    return data or ""


def _invoke_summary_llm(llm, prompt):
    request = BasicLLMRequest(
        openai_api_base=llm.openai_api_base,
        openai_api_key=llm.openai_api_key,
        model=llm.model_name,
        temperature=0.3,
        user_message=prompt,
    )
    return LLMClientFactory.invoke_isolated(request, [{"role": "user", "content": prompt}]) or ""


def _llm_summarize(text, llm_model_id):
    """调用 LLM 生成资料全文摘要;无模型或失败时回退为截断文本。"""
    snippet = (text or "").strip()
    if not snippet:
        return ""
    if not llm_model_id:
        return snippet[:500]
    try:
        llm = LLMModel.objects.get(id=llm_model_id)
        chunks = split_text_for_llm(snippet)
        summaries = []
        for idx, chunk in enumerate(chunks, start=1):
            prompt = (
                "请用简洁中文为下面的资料片段生成摘要,保留关键事实、概念与结论,"
                "作为后续知识构建的上下文。\n"
                "注意:这是同一份资料的分块处理,不得因为只看到当前片段就判断全文结束。\n\n"
                f"# 资料片段 {idx}/{len(chunks)}\n{chunk}\n"
            )
            content = _invoke_summary_llm(llm, prompt).strip()
            if content:
                summaries.append(content)
        if not summaries:
            return snippet[:500]
        if len(summaries) == 1:
            return summaries[0]

        merged = "\n".join(f"{idx}. {summary}" for idx, summary in enumerate(summaries, start=1))
        prompt = "请基于下面的分片摘要生成整份资料的总摘要,去重合并相同信息," "保留贯穿全文的关键事实、概念、结论和重要尾部信息。\n\n" f"# 分片摘要\n{merged}\n"
        content = _invoke_summary_llm(llm, prompt).strip()
        return content or merged[:2000]
    except Exception:
        logger.exception("material 摘要生成失败,回退为截断文本")
        return snippet[:500]


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
    markdown = extract_markdown(material)
    if not markdown:
        material.status = "failed"
        material.error_message = _ingest_failure_reason(material)
        material.save(update_fields=["status", "error_message", "updated_at"])
        return material
    digest = compute_hash(markdown)
    if material.content_hash == digest:
        material.status = "done"
        material.error_message = ""
        material.save(update_fields=["status", "error_message", "updated_at"])
        return material
    locator = save_parsed_markdown(material, markdown, digest)
    version = MaterialVersion.objects.create(material=material, content_locator=locator, content_hash=digest)
    material.current_version = version
    material.content_hash = digest
    material.ai_summary = _llm_summarize(markdown, llm_model_id)
    material.status = "done"
    material.error_message = ""
    material.save(update_fields=["current_version", "content_hash", "ai_summary", "status", "error_message", "updated_at"])
    return material
