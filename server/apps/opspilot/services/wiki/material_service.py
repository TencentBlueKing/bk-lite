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


# 文档型(pdf/docx/pptx):loader 原生抽取文本,OCR 仅增强内嵌图片 → OCR 可选(无 provider 也能取文本)
_OCR_DOC_EXTS = {".pdf", ".docx", ".pptx"}
# 纯图片:内容只有图像 → 必须 OCR
_OCR_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def _ocr_loader_class(ext):
    """惰性导入依赖较重(fitz/tabula 等)的 OCR loader,避免模块加载期引入这些依赖。导入失败返回 None。"""
    try:
        return _import_ocr_loader(ext)
    except Exception:
        logger.exception("OCR loader 导入失败 ext=%s(可能缺少 fitz/tabula/Java 等依赖)", ext)
        return None


def _import_ocr_loader(ext):
    if ext == ".pdf":
        from apps.opspilot.metis.llm.loader.pdf_loader import PDFLoader

        return PDFLoader
    if ext in (".png", ".jpg", ".jpeg"):
        from apps.opspilot.metis.llm.loader.image_loader import ImageLoader

        return ImageLoader
    if ext == ".docx":
        from apps.opspilot.metis.llm.loader.doc_loader import DocLoader

        return DocLoader
    if ext == ".pptx":
        from apps.opspilot.metis.llm.loader.ppt_loader import PPTLoader

        return PPTLoader
    return None


def _build_ocr(material):
    """构建 OCR 实例。优先用已启用的 OCRProvider;否则在本机 Tesseract 可用时回退到本地 OCR
    (无需任何外部服务);都不可用则返回 None。测试可 monkeypatch。"""
    from apps.opspilot.metis.ocr.ocr_manager import OcrManager
    from apps.opspilot.metis.ocr.rapid_ocr import RapidOCR
    from apps.opspilot.metis.ocr.tesseract_ocr import TesseractOCR
    from apps.opspilot.models import OCRProvider

    provider = OCRProvider.objects.filter(enabled=True).first()
    if provider:
        cfg = provider.runtime_ocr_config
        return OcrManager.load_ocr(
            ocr_type=cfg.get("ocr_type"),
            model=cfg.get("model"),
            base_url=cfg.get("base_url") or cfg.get("endpoint"),
            api_key=cfg.get("api_key"),
        )
    # 无云端 OCRProvider:优先本地 RapidOCR(纯 pip,无需服务/系统二进制),否则本机 Tesseract
    if RapidOCR.available():
        return RapidOCR()
    if TesseractOCR.available():
        return TesseractOCR()
    return None


def _extract_file_text(material):
    """文件资料:按扩展名分派 loader。

    - .txt/.md/.csv/.xlsx:无需 OCR;
    - .pdf/.docx/.pptx:loader 原生抽取文本(OCR 仅在已配置时增强内嵌图片),**无 OCRProvider 也能取文本**;
    - 图片(.png/.jpg/.jpeg):必须 OCR,无 provider 返回空串。
    任何解析异常(含缺依赖)优雅返回空串。
    """
    name, data = _read_file(material)
    if not data:
        return ""
    ext = (os.path.splitext(name)[1] or "").lower()

    loader_cls = _FILE_LOADERS.get(ext)
    is_ocr_format = False
    ocr = None
    if not loader_cls and ext in (_OCR_DOC_EXTS | _OCR_IMAGE_EXTS):
        is_ocr_format = True
        ocr = _build_ocr(material)  # 无 provider 时为 None
        if ext in _OCR_IMAGE_EXTS and not ocr:
            logger.info("material %s 图片需 OCR,但环境未配置 OCRProvider", material.id)
            return ""
        loader_cls = _ocr_loader_class(ext)
    if not loader_cls:
        logger.info("material %s 扩展名 %s 暂未支持", material.id, ext)
        return ""

    if isinstance(data, str):
        data = data.encode("utf-8")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        docs = loader_cls(tmp_path, ocr, "full").load() if is_ocr_format else loader_cls(tmp_path).load()
        return _docs_to_text(docs)
    except Exception:
        logger.exception("material %s 文件解析失败 ext=%s", material.id, ext)
        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _fetch_url(url):
    """抓取网页 HTML(测试可 monkeypatch 本函数避免真实网络)。"""
    import requests

    resp = requests.get(url, timeout=30, headers={"User-Agent": "bklite-wiki/1.0"})
    resp.raise_for_status()
    return resp.text


def _html_to_text(html):
    """用标准库剥离 HTML 标签为纯文本(忽略 script/style),无需第三方依赖。"""
    from html.parser import HTMLParser

    class _Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self._skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self._skip = False

        def handle_data(self, data):
            if not self._skip and data.strip():
                self.parts.append(data.strip())

    parser = _Stripper()
    parser.feed(html or "")
    return "\n".join(parser.parts)


def _extract_web_text(material):
    """网页资料:抓取 URL → 剥离 HTML 为文本(基础版,不含 JS 渲染/图片 OCR)。"""
    if not material.url:
        return ""
    try:
        html = _fetch_url(material.url)
    except Exception:
        logger.exception("material %s 网页抓取失败 url=%s", material.id, material.url)
        return ""
    return _html_to_text(html)


def extract_text(material):
    """从 Material 提取纯文本正文。

    返回提取到的文本;无法处理的类型/格式返回空串(由调用方决定状态)。
    """
    if material.material_type == "text":
        return _docs_to_text(RawLoader(material.text_content or "").load())
    if material.material_type == "file":
        return _extract_file_text(material)
    if material.material_type == "web":
        return _extract_web_text(material)
    logger.info("material %s type=%s 暂未支持解析", material.id, material.material_type)
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


def _ingest_failure_reason(material):
    """text 为空时给出贴合实际的失败原因,区分:未上传文件 / 无法抽取 / 抓取失败 / 类型不支持。

    旧实现统一返回"暂不支持的资料类型解析: file",会把"文件没传上来"误报成"类型不支持",误导排查。
    """
    mt = material.material_type
    if mt == "file":
        if not material.file:
            return "文件资料未上传文件,无法解析"
        ext = (os.path.splitext(getattr(material.file, "name", "") or material.name)[1] or "").lower()
        if ext in _OCR_IMAGE_EXTS:
            return "图片资料未能识别出文本,请在 OCR 设置中启用 OCR 后重试"
        return "未能从文件中提取到文本(文件可能为空、损坏,或为需 OCR 的扫描件)"
    if mt == "web":
        if not material.url:
            return "网页资料缺少 URL,无法解析"
        return "未能抓取到网页正文(URL 不可达或页面无可提取内容)"
    if mt == "text":
        return "文本内容为空"
    return f"暂不支持的资料类型: {mt}"


def ingest_material(material, llm_model_id=None):
    """解析资料 + 生成摘要 + 更新状态。返回更新后的 material。"""
    text = extract_text(material)
    if not text:
        material.status = "failed"
        material.error_message = _ingest_failure_reason(material)
        material.save(update_fields=["status", "error_message", "updated_at"])
        return material
    material.content_hash = compute_hash(text)
    material.ai_summary = _llm_summarize(text, llm_model_id)
    material.status = "done"
    material.error_message = ""
    material.save(update_fields=["content_hash", "ai_summary", "status", "error_message", "updated_at"])
    return material
