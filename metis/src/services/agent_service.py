from neco.llm.chain.entity import BasicLLMRequest
from src.core_settings import core_settings


class AgentService:

    @classmethod
    def prepare_request(cls, req: BasicLLMRequest):
        req.extra_config['graph_rag_host'] = core_settings.knowledge_graph_host
        req.extra_config['graph_rag_username'] = core_settings.knowledge_graph_username
        req.extra_config['graph_rag_password'] = core_settings.knowledge_graph_password
        req.extra_config['graph_rag_port'] = core_settings.knowledge_graph_port
        req.extra_config['graph_rag_database'] = core_settings.knowledge_graph_database
        req.extra_config['naive_rag_db_url'] = core_settings.db_uri

        for i in req.naive_rag_request:
            i.search_query = req.user_message
