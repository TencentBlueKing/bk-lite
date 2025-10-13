from sanic import Blueprint, json
from sanic_ext import validate

from neco.sanic.auth.api_auth import auth
from neco.llm.rag.rag_enhance_entity import AnswerGenerateRequest, QAEnhanceRequest, QuestionGenerateRequest
from neco.mlops.summarize.summarize_manager import SummarizeManager, SummarizeRequest
from src.services.qa_enhance_service import QAEnhanceService
rag_enhance_api_router = Blueprint("rag_enhance_api_router", url_prefix="/rag")


@rag_enhance_api_router.post("/summarize_enhance")
@auth.login_required
@validate(json=SummarizeRequest)
async def summarize_enhance(request, body: SummarizeRequest):
    result = SummarizeManager.summarize(body)
    return json({"status": "success", "message": result})


@rag_enhance_api_router.post("/qa_pair_generate")
@auth.login_required
@validate(json=QAEnhanceRequest)
async def qa_pair_generate(request, body: QAEnhanceRequest):
    result = QAEnhanceService.generate_qa(body)
    return json({"status": "success", "message": result})


@rag_enhance_api_router.post("/question_generation")
@auth.login_required
@validate(json=QuestionGenerateRequest)
async def question_generation(request, body: QuestionGenerateRequest):
    result = QAEnhanceService.generate_question(body)
    return json({"status": "success", "message": result})


@rag_enhance_api_router.post("/answer_generation")
@auth.login_required
@validate(json=AnswerGenerateRequest)
async def answer_generation(request, body: AnswerGenerateRequest):
    result = QAEnhanceService.generate_answer(body)
    return json({"status": "success", "message": result})
