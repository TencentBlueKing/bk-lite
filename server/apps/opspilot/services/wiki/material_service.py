"""资料(Material)摄取:解析为文本 + 生成 AI 摘要。

支持:text(纯文本)、file 中的 .txt/.md(经 loader 解析)。
PDF/Office/图片/网页等依赖 OCR/抓取的解析仍待接入(loader 已就绪,需 OCRProvider + 网络),
此类返回空串,由调用方标记 failed。
"""

import hashlib
import logging
import os
import tempfile

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.metis.llm.loader.excel_loader import ExcelLoader
from apps.opspilot.metis.llm.loader.markdown_loader import MarkdownLoader
from apps.opspilot.metis.llm.loader.raw_loader import RawLoader
from apps.opspilot.metis.llm.loader.text_loader import TextLoader
from apps.opspilot.models import LLMModel

logger = logging.getLogger("opspilot")

# 无需 OCR、可直接经 loader 解析的文件扩展名 → loader 类
_FILE_LOADERS = {
    ".txt": TextLoader,
    ".text": TextLoader,
    ".csv": TextLoader,
    ".md": MarkdownLoader,
    ".markdown": MarkdownLoader,
    ".xlsx": ExcelLoader,
    ".xls": ExcelLoader,
}


def _docs_to_text(docs):
    parts = []
    for d in docs or []:
        content = getattr(d, "page_content", "") or ""
        if content.strip():
            parts.append(content)
    return "\n\n".join(parts)


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


def _extract_file_text(material):
    """文件资料:按扩展名选 loader(仅 .txt/.md 无需 OCR),写临时文件解析。其余返回空串。"""
    name, data = _read_file(material)
    ext = (os.path.splitext(name)[1] or "").lower()
    loader_cls = _FILE_LOADERS.get(ext)
    if not loader_cls:
        logger.info("material %s 扩展名 %s 需 OCR/暂未支持,待后续接入", material.id, ext)
        return ""
    if isinstance(data, str):
        data = data.encode("utf-8")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        return _docs_to_text(loader_cls(tmp_path).load())
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def extract_text(material):
    """从 Material 提取纯文本正文。

    返回提取到的文本;无法处理的类型/格式返回空串(由调用方决定状态)。
    """
    if material.material_type == "text":
        return _docs_to_text(RawLoader(material.text_content or "").load())
    if material.material_type == "file":
        return _extract_file_text(material)
    # web 等需要抓取/OCR 的解析在后续增量接入
    logger.info("material %s type=%s 暂未支持解析(后续增量接入)", material.id, material.material_type)
    return ""


def compute_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _llm_summarize(text, llm_model_id):
    """调用 LLM 生成资料摘要;无模型或失败时回退为截断文本。"""
    snippet = (text or "").strip()
    if not llm_model_id:
        return snippet[:500]
    try:
        llm = LLMModel.objects.get(id=llm_model_id)
        prompt = "请用简洁中文为下面的资料生成一份摘要,保留关键事实、概念与结论,作为后续知识构建的上下文。\n\n" f"# 资料正文\n{snippet[:8000]}\n"
        request = BasicLLMRequest(
            openai_api_base=llm.openai_api_base,
            openai_api_key=llm.openai_api_key,
            model=llm.model_name,
            temperature=0.3,
            user_message=prompt,
        )
        content = LLMClientFactory.invoke_isolated(request, [{"role": "user", "content": prompt}])
        return (content or "").strip() or snippet[:500]
    except Exception:
        logger.exception("material 摘要生成失败,回退为截断文本")
        return snippet[:500]


def ingest_material(material, llm_model_id=None):
    """解析资料 + 生成摘要 + 更新状态。返回更新后的 material。"""
    text = extract_text(material)
    if not text:
        material.status = "failed"
        material.error_message = f"暂不支持的资料类型解析: {material.material_type}"
        material.save(update_fields=["status", "error_message", "updated_at"])
        return material
    material.content_hash = compute_hash(text)
    material.ai_summary = _llm_summarize(text, llm_model_id)
    material.status = "done"
    material.error_message = ""
    material.save(update_fields=["content_hash", "ai_summary", "status", "error_message", "updated_at"])
    return material
