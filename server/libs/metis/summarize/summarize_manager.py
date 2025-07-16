
import logging

from libs.metis.summarize.textrank.textrank_sentence import TextRankSentence
logger = logging.getLogger(__name__)


class SummarizeManager:
    @classmethod
    def summarize(cls, content: str, model: str, openai_api_base: str,
                  openai_api_key: str, ) -> str:
        if model.startswith('local:'):
            local_model = model.split(':')[1]
            if local_model == 'textrank':
                text_rank_model = TextRankSentence()
                text_rank_model.analyze(text=content, lower=True, source='all_filters')
                items = text_rank_model.get_key_sentences(num=1)
                return items[0].sentence
