from neco.mlops.summarize.textrank.textrank_sentence import TextRankSentence
from loguru import logger
from typing import Optional
from pydantic import BaseModel

class SummarizeRequest(BaseModel):
    content: str
    model: str = 'local:textrank'
    algorithm_args: Optional[dict] = {}


class SummarizeManager:
    @classmethod
    def summarize(cls, req: SummarizeRequest) -> str:
        if req.model.startswith('local:'):
            local_model = req.model.split(':')[1]
            if local_model == 'textrank':
                text_rank_model = TextRankSentence()
                text_rank_model.analyze(text=req.content, lower=True, source='all_filters')
                items = text_rank_model.get_key_sentences(num=1)
                return items[0].sentence

        logger.warning(f"没有找到对应的摘要模型: {req.model}, 使用默认的内容返回")
        return req.content
