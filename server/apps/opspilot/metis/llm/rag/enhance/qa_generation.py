import json_repair
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate
from langchain_openai import ChatOpenAI

from apps.opspilot.metis.llm.rag.rag_enhance_entity import AnswerGenerateRequest, QAEnhanceRequest, QuestionGenerateRequest
from apps.opspilot.metis.utils.template_loader import TemplateLoader


class QAGeneration:
    @staticmethod
    def _escape_template_braces(text: str) -> str:
        """转义字符串中的大括号，防止被模板引擎识别为变量

        Args:
            text: 原始文本

        Returns:
            转义后的文本
        """
        if not text:
            return text
        # 将 { 替换为 {{，} 替换为 }}
        return text.replace("{", "{{").replace("}", "}}")

    @classmethod
    def generate_answer(cls, req: AnswerGenerateRequest):
        system_prompt = TemplateLoader.render_template("prompts/answer_generation/system_prompt")
        input_prompt = TemplateLoader.render_template(
            "prompts/answer_generation/input_prompt",
            context={
                "context": cls._escape_template_braces(req.context),
                "text": cls._escape_template_braces(req.content),
                "extra_prompt": cls._escape_template_braces(req.extra_prompt),
            },
        )

        llm = ChatOpenAI(model=req.model, base_url=req.openai_api_base, api_key=req.openai_api_key, temperature="0")

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(system_prompt),
                HumanMessagePromptTemplate.from_template(input_prompt),
            ]
        )

        chain = prompt | llm
        result = chain.invoke({})
        return json_repair.loads(result.content)

    @staticmethod
    def generate_question(req: QuestionGenerateRequest):
        system_prompt = TemplateLoader.render_template("prompts/question_generation/system_prompt")
        input_prompt = TemplateLoader.render_template(
            "prompts/question_generation/input_prompt",
            context={
                "text": QAGeneration._escape_template_braces(req.content),
                "size": req.size,
                "extra_prompt": QAGeneration._escape_template_braces(req.extra_prompt),
            },
        )

        llm = ChatOpenAI(model=req.model, base_url=req.openai_api_base, api_key=req.openai_api_key, temperature="0")

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(system_prompt),
                HumanMessagePromptTemplate.from_template(input_prompt),
            ]
        )

        chain = prompt | llm
        result = chain.invoke({})
        return json_repair.loads(result.content)

    @staticmethod
    def generate_qa(req: QAEnhanceRequest):
        system_prompt = TemplateLoader.render_template("prompts/qa_pair/system_prompt")
        input_prompt = TemplateLoader.render_template(
            "prompts/qa_pair/input_prompt",
            context={
                "text": QAGeneration._escape_template_braces(req.content),
                "size": req.size,
                "extra_prompt": QAGeneration._escape_template_braces(req.extra_prompt),
            },
        )

        llm = ChatOpenAI(model=req.model, base_url=req.openai_api_base, api_key=req.openai_api_key, temperature="0")

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(system_prompt),
                HumanMessagePromptTemplate.from_template(input_prompt),
            ]
        )

        chain = prompt | llm
        result = chain.invoke({})
        return json_repair.loads(result.content)
