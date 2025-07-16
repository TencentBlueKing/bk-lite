from typing import List

from langchain_core.documents import Document

class ReRankManager:
    _rerank_instance = {}

    @classmethod
    def get_rerank_instance(cls, protocol: str):
        """
        Get the rerank instance based on the protocol.
        :param protocol: The protocol string.
        :return: The rerank instance.
        """
        model_type = protocol.split(':')[1]
        model_name = protocol.split(':')[2]

        if model_type == 'bce' and cls._rerank_instance.get(protocol, None) is None:
            from libs.metis.rerank.bce_rerank import BCEReRank
            cls._rerank_instance[protocol] = BCEReRank(model_name_or_path=model_name)
        return cls._rerank_instance[protocol]

    @staticmethod
    def rerank(protocol: str, query: str, docs: List[Document]):
        """
        Rerank the documents based on the query.
        :param protocol: The protocol string.
        :param query: The query string.
        :param docs: The list of documents to rerank.
        :param top_n: The number of top documents to return.
        :return: The reranked documents.
        """
        model_type = protocol.split(':')[1]

        passages = []
        for doc in docs:
            passages.append(doc.page_content)

        rerank = ReRankManager.get_rerank_instance(protocol)

        if model_type == 'bce':
            result = rerank.rerank(query, passages)
            return result

