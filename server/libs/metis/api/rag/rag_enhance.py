
from libs.metis.enhance.qa_enhance import QAEnhance
from libs.metis.entity.rag.enhance.qa_enhance_request import QAEnhanceRequest
from libs.metis.entity.rag.enhance.summarize_enhance_request import SummarizeEnhanceRequest
from libs.metis.summarize.summarize_manager import SummarizeManager


async def summarize_enhance(body: SummarizeEnhanceRequest):
    """
    文本摘要增强
    :param request:
    :param body:
    :return:
    """
    """
    文本摘要增强
    :param request:
    :param body:
    :return:
    """
    result = SummarizeManager.summarize(
        body.content, body.model, body.openai_api_base, body.openai_api_key)
    return result


async def qa_pair_generate(body: QAEnhanceRequest):
    """
    QA 问答对生成
    :param request:
    :return:
    """
    """
    生成问答对
    :param request:
    :return:
    """
    qa_enhance = QAEnhance(body)
    result = qa_enhance.generate_qa()
    return result
