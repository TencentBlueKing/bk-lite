"""资料(Material)摄取:解析为文本 + 生成 AI 摘要。

P1 首个增量:支持 text / markdown / 纯文本提取与摘要。
PDF/Office/网页等依赖 OCR 的解析在后续增量接入(loader 已就绪,见 metis/llm/loader)。
"""

import hashlib
import logging

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.metis.llm.loader.raw_loader import RawLoader
from apps.opspilot.models import LLMModel

logger = logging.getLogger("opspilot")

_SUPPORTED_TEXT_TYPES = {"text"}


def _docs_to_text(docs):
    parts = []
    for d in docs or []:
        content = getattr(d, "page_content", "") or ""
        if content.strip():
            parts.append(content)
    return "\n\n".join(parts)


def extract_text(material):
    """从 Material 提取纯文本正文。

    返回提取到的文本;无法处理的类型返回空串(由调用方决定状态)。
    """
    if material.material_type == "text":
        return _docs_to_text(RawLoader(material.text_content or "").load())
    # file / web 等需要 OCR 的解析在后续增量接入
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
