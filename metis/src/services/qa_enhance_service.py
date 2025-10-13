
from neco.llm.rag.rag_enhance_entity import AnswerGenerateRequest, QAEnhanceRequest, QuestionGenerateRequest
from neco.llm.rag.enhance.qa_generation import QAGeneration


class QAEnhanceService:
    @staticmethod
    def generate_answer(req: AnswerGenerateRequest):
        return QAGeneration.generate_answer(req)

    @staticmethod
    def generate_question(req: QuestionGenerateRequest):
        return QAGeneration.generate_question(req)

    @staticmethod
    def generate_qa(req: QAEnhanceRequest):
        return QAGeneration.generate_qa(req)
