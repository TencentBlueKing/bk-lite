from libs.metis.entity.rag.graphiti.index_delete_request import IndexDeleteRequest
from libs.metis.entity.rag.graphiti.document_delete_request import DocumentDeleteRequest
from libs.metis.entity.rag.graphiti.document_ingest_request import GraphitiRagDocumentIngestRequest
from libs.metis.entity.rag.graphiti.document_retriever_request import DocumentRetrieverRequest
from libs.metis.entity.rag.graphiti.rebuild_community_request import RebuildCommunityRequest
from libs.metis.rag.graph_rag.graphiti.graphiti_rag import GraphitiRAG

async def ingest(body: GraphitiRagDocumentIngestRequest):
    rag = GraphitiRAG()
    rs = await rag.ingest(body)
    return rs


async def rebuild_community(body: RebuildCommunityRequest):
    rag = GraphitiRAG()
    await rag.rebuild_community(body)


async def search(body: DocumentRetrieverRequest):
    rag = GraphitiRAG()
    result = await rag.search(body)
    return result


async def list_index_documents(body: DocumentRetrieverRequest):
    rag = GraphitiRAG()
    result = await rag.list_index_document(body)
    return result


async def delete_document(body: DocumentDeleteRequest):
    rag = GraphitiRAG()
    await rag.delete_document(body)


async def delete_index(body: IndexDeleteRequest):
    rag = GraphitiRAG()
    await rag.delete_index(body)
