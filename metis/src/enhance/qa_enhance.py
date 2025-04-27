import json
import re
from loguru import logger
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate


class QAEnhance:
    def __init__(self, size: int = 1):
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
                generate {size} Q&A Pair
        """

    def _extract_json_from_markdown(self, text):
        """从可能包含markdown代码块的文本中提取JSON内容"""
        # 尝试匹配markdown代码块
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            json_str = match.group(1)
        else:
            json_str = text

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # 如果解析失败，返回原始文本
            return {"question": "解析失败", "answer": text}

    def generate_qa(self, llm, content):
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(self.system_prompt),
                HumanMessagePromptTemplate.from_template(self.input_prompt),
            ]
        )

        chain = prompt | llm
        result = chain.invoke({"text": content})
        return self._extract_json_from_markdown(result.content)
