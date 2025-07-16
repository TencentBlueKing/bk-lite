import json_repair
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_openai import ChatOpenAI

from libs.metis.entity.rag.enhance.qa_enhance_request import QAEnhanceRequest


class QAEnhance:
    def __init__(self, req: QAEnhanceRequest):
        self.system_prompt = '''You are a smart assistant designed to help high school teachers come up with reading comprehension questions.
        Given a piece of text, you must come up with a question and answer pair that can be used to test a student's reading comprehension abilities.
        When coming up with this question/answer pair, you must respond in the following format:
        ```
        [{{
            "question": "$YOUR_QUESTION_HERE",
            "answer": "$THE_ANSWER_HERE"
        }}]
        ```

        Everything between the ``` must be valid json.
        answer in Chinese.
        '''
        self.input_prompt = '''Please come up with a question/answer pair, in the specified JSON format, for the following text:
        ----------------
        {text}
        ----------------
        
        '''
        self.input_prompt += f"""
                generate {req.size} Q&A Pair
        """
        self.req = req
        self.llm = ChatOpenAI(model=req.model, base_url=req.openai_api_base,
                              api_key=req.openai_api_key,
                              temperature="0")



    def generate_qa(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(self.system_prompt),
                HumanMessagePromptTemplate.from_template(self.input_prompt),
            ]
        )

        chain = prompt | self.llm
        result = chain.invoke({"text": self.req.content})
        return json_repair.loads(result.content)
