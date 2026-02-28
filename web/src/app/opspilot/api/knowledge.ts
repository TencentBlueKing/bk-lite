import useApiClient from '@/utils/request';
import type { 
  KnowledgeValues,
  EmbeddingModel,
  RerankModel,
  OcrModel,
  KnowledgeBaseListParams,
  KnowledgeBaseListResponse,
  DocumentListParams,
  DocumentListResponse,
  QAPairListParams,
  QAPairListResponse,
  KnowledgeBaseDetails,
  DocumentDetail,
  KnowledgeSettings,
  TestKnowledgeParams,
  TestKnowledgeResponse,
  AnnotationPayload,
  ParseContentParams,
  WebPageKnowledgeParams,
  ManualKnowledgeParams,
  DocumentConfigResponse,
  TaskItem,
  QAPairTaskStatus,
  ChunkDetail,
  KnowledgeGraphDetails,
  KnowledgeGraphConfig,
  QAPairDetailResponse,
  GeneratedQuestion,
  GeneratedAnswer,
} from '@/app/opspilot/types/knowledge';

export const useKnowledgeApi = () => {
  const { get, post, patch, del } = useApiClient();

  const fetchEmbeddingModels = async (): Promise<EmbeddingModel[]> => {
    return get('/opspilot/model_provider_mgmt/embed_provider/', { params: { enabled: 1 } });
  };

  const fetchKnowledgeBase = async (params: KnowledgeBaseListParams): Promise<KnowledgeBaseListResponse> => {
    return get('/opspilot/knowledge_mgmt/knowledge_base/', { params });
  };

  const addKnowledge = async (values: KnowledgeValues): Promise<KnowledgeValues & { id: number }> => {
    return post('/opspilot/knowledge_mgmt/knowledge_base/', values);
  };

  const updateKnowledge = async (id: number, values: KnowledgeValues): Promise<void> => {
    return patch(`/opspilot/knowledge_mgmt/knowledge_base/${id}/`, values);
  };

  const deleteKnowledge = async (id: number): Promise<void> => {
    return del(`/opspilot/knowledge_mgmt/knowledge_base/${id}/`);
  };

  const updateKnowledgeSettings = async (id: string | null, params: KnowledgeSettings): Promise<void> => {
    if (!id) throw new Error('Knowledge base ID is required');
    return post(`/opspilot/knowledge_mgmt/knowledge_base/${id}/update_settings/`, params);
  };

  const fetchDocuments = async (params: DocumentListParams): Promise<DocumentListResponse> => {
    return get('/opspilot/knowledge_mgmt/knowledge_document/', { params });
  };

  const batchDeleteDocuments = async (docIds: React.Key[], knowledgeBaseId: string | null): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/batch_delete/', {
      doc_ids: docIds,
      knowledge_base_id: knowledgeBaseId,
    });
  };

  const batchTrainDocuments = async (docIds: React.Key[], deleteQaPairs: boolean = true): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/batch_train/', {
      knowledge_document_ids: docIds,
      delete_qa_pairs: deleteQaPairs,
    });
  };

  const updateDocumentBaseInfo = async (documentId: number, params: { name?: string; chunk_size?: number; chunk_overlap?: number }): Promise<void> => {
    return post(`/opspilot/knowledge_mgmt/knowledge_document/${documentId}/update_document_base_info/`, params);
  };

  const createWebPageKnowledge = async (knowledgeBaseId: string | null, params: WebPageKnowledgeParams): Promise<number> => {
    return post('/opspilot/knowledge_mgmt/web_page_knowledge/create_web_page_knowledge/', {
      knowledge_base_id: knowledgeBaseId,
      ...params,
    });
  };

  const createFileKnowledge = async (formData: FormData): Promise<number[]> => {
    return post('/opspilot/knowledge_mgmt/file_knowledge/create_file_knowledge/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  };

  const createManualKnowledge = async (knowledgeBaseId: string | null, params: ManualKnowledgeParams): Promise<number> => {
    return post('/opspilot/knowledge_mgmt/manual_knowledge/create_manual_knowledge/', {
      knowledge_base_id: knowledgeBaseId,
      ...params,
    });
  };

  const getDocumentDetail = async (documentId: number): Promise<DocumentDetail> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_document/${documentId}/get_document_detail/`);
  };

  const getInstanceDetail = async (documentId: number): Promise<DocumentDetail> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_document/${documentId}/get_instance_detail/`);
  };

  const fetchDocumentDetails = async (
    knowledgeId: string,
    page: number,
    pageSize: number,
    searchTerm: string
  ): Promise<{ count: number; items: ChunkDetail[] }> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_document/${knowledgeId}/get_detail/`, {
      params: {
        page,
        page_size: pageSize,
        search_term: searchTerm,
      },
    });
  };

  const fetchSemanticModels = async (): Promise<RerankModel[]> => {
    return get('/opspilot/model_provider_mgmt/rerank_provider/', { params: { enabled: 1 } });
  };

  const fetchOcrModels = async (): Promise<OcrModel[]> => {
    return get('/opspilot/model_provider_mgmt/ocr_provider/');
  };

  const fetchPreviewData = async (config: Record<string, unknown>): Promise<string[]> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/preprocess/', config);
  };

  const testKnowledge = async (params: TestKnowledgeParams): Promise<TestKnowledgeResponse> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/testing', params);
  };

  const fetchKnowledgeBaseDetails = async (id: number): Promise<KnowledgeBaseDetails> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_base/${id}/`);
  };

  const saveAnnotation = async (payload: AnnotationPayload): Promise<{ id: number; tag_id?: string | number }> => {
    return post('/opspilot/bot_mgmt/history/set_tag', payload);
  };

  const removeAnnotation = async (tagId: string | number | undefined): Promise<void> => {
    return post('/opspilot/bot_mgmt/history/remove_tag/', { tag_id: tagId });
  };

  const parseContent = async (params: ParseContentParams): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/update_parse_settings/', params);
  };

  const updateChunkSettings = async (params: {
    knowledge_source_type: string;
    knowledge_document_list: number[];
    chunk_size: number;
    chunk_overlap: number;
    semantic_embedding_model: number | null;
    chunk_type: string;
  }): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/update_chunk_settings/', params);
  };

  const previewChunk = async (params: {
    knowledge_source_type: string;
    knowledge_document_id: number;
    general_parse_chunk_size: number;
    general_parse_chunk_overlap: number;
    semantic_chunk_parse_embedding_model: number | null;
    chunk_type: string;
  }): Promise<string[]> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/preview_chunk/', params);
  };

  const getDocListConfig = async (params: { knowledge_document_ids?: number[]; doc_ids?: number[] }): Promise<DocumentConfigResponse[]> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/get_doc_list_config/', params);
  };

  const getDocumentConfig = async (id: number): Promise<DocumentConfigResponse> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_document/${id}/`);
  };

  const fetchMyTasks = async (params: { page?: number; page_size?: number }): Promise<TaskItem[]> => {
    return get('/opspilot/knowledge_mgmt/knowledge_document/get_my_tasks/',  { params });
  };

  const fetchQAPairsTaskStatus = async (params: { document_id: string }): Promise<QAPairTaskStatus[]> => {
    return get('/opspilot/knowledge_mgmt/qa_pairs/get_qa_pairs_task_status/', { params });
  };

  const fetchQAPairs = async (params: QAPairListParams): Promise<QAPairListResponse> => {
    return get('/opspilot/knowledge_mgmt/qa_pairs/', { params });
  };

  const deleteQAPair = async (qaPairId: number): Promise<void> => {
    return del(`/opspilot/knowledge_mgmt/qa_pairs/${qaPairId}/`);
  };

  const createOneQAPair = async (payload: {
    knowledge_id: number;
    qa_pairs_id: number;
    question: string;
    answer: string;
  }): Promise<{ id: string }> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/create_one_qa_pairs/', payload);
  };

  const createQAPairs = async (payload: {
    knowledge_base_id: number;
    llm_model_id: number;
    qa_count: number;
    document_list: Array<{
      name: string;
      document_id: number;
      document_source: string;
    }>;
  }): Promise<{ id: number }> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/create_qa_pairs/', payload);
  };

  const updateQAPair = async (payload: {
    qa_pairs_id: number;
    id: string;
    question: string;
    answer: string;
  }): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/update_qa_pairs/', payload);
  };

  const deleteOneQAPair = async (payload: {
    qa_pairs_id: number;
    id: string;
  }): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/delete_one_qa_pairs/', payload);
  };

  const createCustomQAPairs = async (payload: {
    knowledge_base_id: number;
    name: string;
    qa_pairs: Array<{
      question: string;
      answer: string;
    }>;
  }): Promise<{ id: number }> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/create_qa_pairs_by_custom/', payload);
  };

  const createQAPairsByChunk = async (payload: {
    name: string;
    knowledge_base_id: number;
    document_id: number;
    document_source: string;
    qa_count: number;
    llm_model_id: number;
    answer_llm_model_id: number;
    question_prompt: string;
    answer_prompt: string;
    only_question?: boolean;
    chunk_list: Array<{
      content: string;
      id: string;
    }>;
  }): Promise<{ id: number }> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/create_qa_pairs_by_chunk/', payload);
  };

  const fetchQAPairDetails = async (params: {
    qa_pair_id: number;
    page?: number;
    page_size?: number;
    search_text?: string;
  }): Promise<{ count: number; items: Array<{ id: string; question: string; answer: string }> }> => {
    return get(`/opspilot/knowledge_mgmt/qa_pairs/${params.qa_pair_id}/get_details/`, { params });
  };

  const fetchChunkQAPairs = async (indexName: string, chunkId: string, knowledgeBaseId: number | undefined): Promise<Array<{ id: string; question: string; answer: string }>> => {
    return get('/opspilot/knowledge_mgmt/qa_pairs/get_chunk_qa_pairs/', {
      params: {
        index_name: indexName,
        chunk_id: chunkId,
        knowledge_base_id: knowledgeBaseId
      },
    });
  };

  const fetchKnowledgeGraphDetails = async (knowledgeBaseId: number): Promise<KnowledgeGraphDetails> => {
    return get('/opspilot/knowledge_mgmt/knowledge_graph/get_details/', {
      params: {
        knowledge_base_id: knowledgeBaseId,
      },
    });
  };

  const fetchKnowledgeGraphById = async (graphId: number): Promise<KnowledgeGraphConfig> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_graph/${graphId}/`);
  };

  const saveKnowledgeGraph = async (payload: {
    knowledge_base: number;
    llm_model: number;
    rerank_model: number;
    embed_model: number;
    doc_list: Array<{
      id: number;
      source: string;
    }>;
  }): Promise<{ id: number }> => {
    return post('/opspilot/knowledge_mgmt/knowledge_graph/', payload);
  };

  const updateKnowledgeGraph = async (graphId: number, payload: {
    knowledge_base: number;
    llm_model: number;
    rerank_model: number;
    embed_model: number;
    doc_list: Array<{
      id: number;
      source: string;
    }>;
  }): Promise<void> => {
    return patch(`/opspilot/knowledge_mgmt/knowledge_graph/${graphId}/`, payload);
  };

  const rebuildKnowledgeGraphCommunity = async (knowledgeBaseId: number): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/knowledge_graph/rebuild_graph_community/', {
      knowledge_base_id: knowledgeBaseId,
    });
  };

  const importQaJson = async (formData: FormData): Promise<number[]> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/import_qa_json/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  };

  const getChunkDetail = async (
    knowledge_id: string,
    chunk_id: string | null,
    type: 'Document' | 'QA' | 'Graph' = 'Document'
  ): Promise<ChunkDetail> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_document/get_chunk_detail/`, { 
      params: {
        knowledge_id,
        chunk_id,
        type,
      },
    });
  };

  const deleteChunks = async (payload: {
    knowledge_base_id: number;
    ids: string[];
    delete_all: boolean;
  }): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/delete_chunks/', payload);
  };

  const generateQuestions = async (payload: {
    document_list: Array<{ document_id: number }>;
    knowledge_base_id: number;
    llm_model_id: number;
    question_prompt: string;
  }): Promise<GeneratedQuestion[]> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/generate_question/', payload);
  };

  const generateAnswers = async (payload: {
    answer_llm_model_id: number;
    answer_prompt: string;
    knowledge_base_id: number;
    question_data: GeneratedQuestion[];
  }): Promise<GeneratedAnswer[]> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/generate_answer/', payload);
  };

  const generateAnswerToEs = async (payload: {
    qa_pairs_id: number;
  }): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/generate_answer_to_es/', payload);
  };

  const getQAPairDetail = async (qaPairId: number): Promise<QAPairDetailResponse> => {
    return get(`/opspilot/knowledge_mgmt/qa_pairs/${qaPairId}/`);
  };

  const updateQAPairConfig = async (qaPairId: number, payload: {
    llm_model_id: number;
    qa_count: number;
    question_prompt: string;
    answer_prompt: string;
    answer_llm_model_id: number;
    only_question?: boolean;
  }): Promise<void> => {
    return patch(`/opspilot/knowledge_mgmt/qa_pairs/${qaPairId}/`, payload);
  };

  const previewQAPairs = async (payload: {
    chunk_list: Array<{
      chunk_id: string;
      content: string;
      knowledge_id: string;
    }>;
    knowledge_base_id: number;
    llm_model_id: number;
    qa_count: number;
    question_prompt: string;
    answer_llm_model_id: number;
    answer_prompt: string;
  }): Promise<GeneratedAnswer[]> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/preview/', payload);
  };

  return {
    fetchEmbeddingModels,
    fetchKnowledgeBase,
    addKnowledge,
    updateKnowledge,
    deleteKnowledge,
    updateKnowledgeSettings,
    fetchDocuments,
    batchDeleteDocuments,
    batchTrainDocuments,
    updateDocumentBaseInfo,
    createWebPageKnowledge,
    createFileKnowledge,
    createManualKnowledge,
    getDocumentDetail,
    getInstanceDetail,
    fetchDocumentDetails,
    fetchSemanticModels,
    fetchOcrModels,
    fetchPreviewData,
    testKnowledge,
    fetchKnowledgeBaseDetails,
    saveAnnotation,
    removeAnnotation,
    parseContent,
    updateChunkSettings,
    previewChunk,
    getDocListConfig,
    getDocumentConfig,
    fetchMyTasks,
    fetchQAPairsTaskStatus,
    fetchQAPairs,
    deleteQAPair,
    createOneQAPair,
    updateQAPair,
    deleteOneQAPair,
    createQAPairs,
    createCustomQAPairs,
    createQAPairsByChunk,
    fetchQAPairDetails,
    fetchChunkQAPairs,
    fetchKnowledgeGraphDetails,
    fetchKnowledgeGraphById,
    saveKnowledgeGraph,
    updateKnowledgeGraph,
    rebuildKnowledgeGraphCommunity,
    importQaJson,
    getChunkDetail,
    deleteChunks,
    generateQuestions,
    generateAnswers,
    generateAnswerToEs,
    getQAPairDetail,
    updateQAPairConfig,
    previewQAPairs,
  };
};
