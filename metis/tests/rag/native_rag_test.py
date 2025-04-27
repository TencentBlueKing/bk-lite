import os

from langchain_core.documents import Document

from dotenv import load_dotenv
from loguru import logger

from src.rag.native_rag.entity.elasticsearch_document_delete_request import ElasticSearchDocumentDeleteRequest
from src.rag.native_rag.entity.elasticsearch_document_metadata_update_request import \
    ElasticsearchDocumentMetadataUpdateRequest
from src.rag.native_rag.entity.elasticsearch_index_delete_request import ElasticSearchIndexDeleteRequest
from src.rag.native_rag.entity.elasticsearch_retriever_request import ElasticSearchRetrieverRequest
from src.rag.native_rag.entity.elasticsearch_store_request import ElasticSearchStoreRequest
from src.rag.native_rag.rag.elasticsearch_rag import ElasticSearchRag


def get_sample_request():
    request = ElasticSearchStoreRequest(
        index_name=os.getenv('TEST_ELASTICSEARCH_RAG_INDEX'),
        index_mode='overwrite',
        docs=[
            Document(page_content='你好', metadata={
                'knowledge_title': '你好', 'knowledge_id': "1"}),
            Document(page_content='介绍一下你自己', metadata={
                'knowledge_title': '介绍一下你自己', 'knowledge_id': "2"}),
            Document(page_content='你是谁', metadata={
                'knowledge_title': '你是谁', 'knowledge_id': "3"}),
            Document(page_content='你会什么', metadata={
                'knowledge_title': '你会什么', 'knowledge_id': "4"}),
            Document(page_content='你能做什么', metadata={
                'knowledge_title': '你能做什么', 'knowledge_id': "5"}),
            Document(page_content='你能帮我做什么', metadata={
                'knowledge_title': '你能帮我做什么', 'knowledge_id': "6"}),
            Document(page_content='你能给我讲个笑话吗', metadata={
                'knowledge_title': '你能给我讲个笑话吗', 'knowledge_id': "7"}),
            Document(page_content='你能给我讲个故事吗', metadata={
                'knowledge_title': '你能给我讲个故事吗', 'knowledge_id': "8"}),
        ],
        embed_model_base_url=os.getenv('TEST_INFERENCE_BASE_URL'),
        embed_model_api_key=os.getenv('TEST_INFERENCE_TOKEN'),
        embed_model_name=os.getenv('TEST_BCE_EMBED_MODEL')
    )
    return request


def test_native_rag_ingest():
    rag = ElasticSearchRag()

    rag.ingest(get_sample_request())

    metadata_update_request= ElasticsearchDocumentMetadataUpdateRequest(
        index_name=os.getenv('TEST_ELASTICSEARCH_RAG_INDEX'),
        metadata_filter={
            'knowledge_id': "8"
        },
        metadata={
            'knowledge_id': "8",
            'demo': '1111'
        }
    )
    rag.update_metadata(metadata_update_request)

    delete_req = ElasticSearchDocumentDeleteRequest(
        index_name=os.getenv('TEST_ELASTICSEARCH_RAG_INDEX'),
        metadata_filter={
            'knowledge_id': "8"
        }
    )
    rag.delete_document(delete_req)

    delete_index_req = ElasticSearchIndexDeleteRequest(
        index_name=os.getenv('TEST_ELASTICSEARCH_RAG_INDEX')
    )
    rag.delete_index(delete_index_req)


def test_native_rag():
    rag = ElasticSearchRag()
    rag.ingest(get_sample_request())

    request = ElasticSearchRetrieverRequest(
        index_name=os.getenv('TEST_ELASTICSEARCH_RAG_INDEX'),
        search_query="你好",
        size=20,
        embed_model_base_url=os.getenv('TEST_INFERENCE_BASE_URL'),
        embed_model_api_key=os.getenv('TEST_INFERENCE_TOKEN'),
        embed_model_name=os.getenv('TEST_BCE_EMBED_MODEL'),
        enable_rerank=True,
        rerank_model_base_url=f'{os.getenv('TEST_INFERENCE_BASE_URL')}/rerank',
        rerank_top_k=5,
        rerank_model_api_key=os.getenv('TEST_INFERENCE_TOKEN'),
        rerank_model_name=os.getenv('TEST_BCE_RERANK_MODEL'),
    )

    result = rag.search(request)
    logger.info(result)

    delete_index_req = ElasticSearchIndexDeleteRequest(
        index_name=os.getenv('TEST_ELASTICSEARCH_RAG_INDEX')
    )
    rag.delete_index(delete_index_req)
