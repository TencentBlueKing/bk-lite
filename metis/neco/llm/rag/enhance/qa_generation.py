from langchain_openai import ChatOpenAI
from neco.core.utils.template_loader import TemplateLoader
from neco.llm.rag.rag_enhance_entity import AnswerGenerateRequest, QAEnhanceRequest, QuestionGenerateRequest
import json_repair
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_openai import ChatOpenAI

class QAGeneration:
    @staticmethod
    def generate_answer(req: AnswerGenerateRequest):
        system_prompt = TemplateLoader.render_template("prompts/answer_generation/system_prompt")
        input_prompt = TemplateLoader.render_template("prompts/answer_generation/input_prompt",
                                                      context={
                                                          "context": req.context,
                                                          "text": req.content,
                                                          "extra_prompt": req.extra_prompt
                                                      })

        llm = ChatOpenAI(model=req.model, base_url=req.openai_api_base,
                         api_key=req.openai_api_key,
                         temperature="0")

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
        system_prompt = TemplateLoader.render_template(
            "prompts/question_generation/system_prompt")
        input_prompt = TemplateLoader.render_template("prompts/question_generation/input_prompt",
                                                      context={
                                                          "text": req.content,
                                                          "size": req.size,
                                                          "extra_prompt": req.extra_prompt
                                                      })

        llm = ChatOpenAI(model=req.model, base_url=req.openai_api_base,
                         api_key=req.openai_api_key,
                         temperature="0")

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
        system_prompt = TemplateLoader.render_template(
            "prompts/qa_pair/system_prompt")
        input_prompt = TemplateLoader.render_template("prompts/qa_pair/input_prompt",
                                                      context={
                                                          "text": req.content,
                                                          "size": req.size,
                                                          "extra_prompt": req.extra_prompt
                                                      })

        llm = ChatOpenAI(model=req.model, base_url=req.openai_api_base,
                         api_key=req.openai_api_key,
                         temperature="0")

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(system_prompt),
                HumanMessagePromptTemplate.from_template(input_prompt),
            ]
        )

        chain = prompt | llm
        result = chain.invoke({})
        return json_repair.loads(result.content)    