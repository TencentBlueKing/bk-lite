import useApiClient from '@/utils/request';
import { KnowledgeValues } from '@/app/opspilot/types/knowledge';

export const useKnowledgeApi = () => {
  const { get, post, patch, del } = useApiClient();

  /**
   * Fetches embedding models.
   */
  const fetchEmbeddingModels = async (): Promise<any[]> => {
    return get('/opspilot/model_provider_mgmt/embed_provider/', { params: { enabled: 1 } });
  };

  /**
   * Fetches the knowledge base.
   */
  const fetchKnowledgeBase = async (params: any): Promise<any> => {
    return get('/opspilot/knowledge_mgmt/knowledge_base/', { params });
  };

  /**
   * Adds a new knowledge entry.
   */
  const addKnowledge = async (values: KnowledgeValues): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/knowledge_base/', values);
  };

  /**
   * Updates an existing knowledge entry.
   */
  const updateKnowledge = async (id: number, values: KnowledgeValues): Promise<void> => {
    return patch(`/opspilot/knowledge_mgmt/knowledge_base/${id}/`, values);
  };

  /**
   * Deletes a knowledge entry.
   */
  const deleteKnowledge = async (id: number): Promise<void> => {
    return del(`/opspilot/knowledge_mgmt/knowledge_base/${id}/`);
  };

  /**
   * Updates knowledge base settings.
   */
  const updateKnowledgeSettings = async (id: string | null, params: any): Promise<void> => {
    if (!id) throw new Error('Knowledge base ID is required');
    return post(`/opspilot/knowledge_mgmt/knowledge_base/${id}/update_settings/`, params);
  };

  /**
   * Fetches documents for the knowledge base.
   */
  const fetchDocuments = async (params: any): Promise<any> => {
    return get('/opspilot/knowledge_mgmt/knowledge_document/', { params });
  };

  /**
   * Deletes multiple documents.
   */
  const batchDeleteDocuments = async (docIds: React.Key[], knowledgeBaseId: string | null): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/batch_delete/', {
      doc_ids: docIds,
      knowledge_base_id: knowledgeBaseId,
    });
  };

  /**
   * Trains multiple documents.
   */
  const batchTrainDocuments = async (docIds: React.Key[], deleteQaPairs: boolean = true): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/batch_train/', {
      knowledge_document_ids: docIds,
      delete_qa_pairs: deleteQaPairs,
    });
  };

  /**
   * Updates document base information.
   */
  const updateDocumentBaseInfo = async (documentId: number, params: any): Promise<void> => {
    return post(`/opspilot/knowledge_mgmt/knowledge_document/${documentId}/update_document_base_info/`, params);
  };

  /**
   * Creates a new web page knowledge entry.
   */
  const createWebPageKnowledge = async (knowledgeBaseId: string | null, params: any): Promise<number> => {
    return post('/opspilot/knowledge_mgmt/web_page_knowledge/create_web_page_knowledge/', {
      knowledge_base_id: knowledgeBaseId,
      ...params,
    });
  };

  /**
   * Creates a new file knowledge entry.
   */
  const createFileKnowledge = async (formData: FormData): Promise<number[]> => {
    return post('/opspilot/knowledge_mgmt/file_knowledge/create_file_knowledge/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  };

  /**
   * Creates a new manual knowledge entry.
   */
  const createManualKnowledge = async (knowledgeBaseId: string | null, params: any): Promise<number> => {
    return post('/opspilot/knowledge_mgmt/manual_knowledge/create_manual_knowledge/', {
      knowledge_base_id: knowledgeBaseId,
      ...params,
    });
  };

  /**
   * Fetches document details.
   */
  const getDocumentDetail = async (documentId: number): Promise<any> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_document/${documentId}/get_document_detail/`);
  };

  const getInstanceDetail = async (documentId: number): Promise<any> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_document/${documentId}/get_instance_detail/`);
  };

  /**
   * Fetches document details with pagination and search.
   */
  const fetchDocumentDetails = async (
    knowledgeId: string,
    page: number,
    pageSize: number,
    searchTerm: string
  ): Promise<{ count: number; items: any[] }> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_document/${knowledgeId}/get_detail/`, {
      params: {
        page,
        page_size: pageSize,
        search_term: searchTerm,
      },
    });
  };

  /**
   * Fetches semantic models.
   */
  const fetchSemanticModels = async (): Promise<any[]> => {
    return get('/opspilot/model_provider_mgmt/rerank_provider/', { params: { enabled: 1 } });
  };

  /**
   * Fetches OCR models.
   */
  const fetchOcrModels = async (): Promise<any[]> => {
    return get('/opspilot/model_provider_mgmt/ocr_provider/');
  };

  /**
   * Fetches preview data for preprocessing.
   */
  const fetchPreviewData = async (config: any): Promise<any[]> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/preprocess/', config);
  };

  /**
   * Tests knowledge base with a query.
   */
  const testKnowledge = async (params: any): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/testing', params);
  };

  /**
   * Fetches knowledge base details by ID.
   */
  const fetchKnowledgeBaseDetails = async (id: number): Promise<{ 
    name: string; 
    introduction: string; 
    permissions: string[];
    file_count?: number;
    web_page_count?: number;
    manual_count?: number;
    qa_count?: number;
    graph_count?: number;
    document_count?: number;
  }> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_base/${id}/`);
  };

  /**
   * Saves an annotation.
   */
  const saveAnnotation = async (payload: any): Promise<any> => {
    return post('/opspilot/bot_mgmt/history/set_tag', payload);
  };

  /**
   * Removes an annotation.
   */
  const removeAnnotation = async (tagId: string | number | undefined): Promise<void> => {
    return post('/opspilot/bot_mgmt/history/remove_tag/', { tag_id: tagId });
  };

  /**
   * Parses content for knowledge documents.
   */
  const parseContent = async (params: any): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/update_parse_settings/', params);
  };

  /**
   * Chunks content for knowledge documents.
   */
  const updateChunkSettings = async (params: {
    knowledge_source_type: string;
    knowledge_document_list: number[];
    chunk_size: number;
    chunk_overlap: number;
    semantic_embedding_model: number | null;
    chunk_type: string;
  }): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/update_chunk_settings/', params);
  };

  /**
   * Previews chunked data for a document.
   */
  const previewChunk = async (params: {
    knowledge_source_type: string;
    knowledge_document_id: number;
    general_parse_chunk_size: number;
    general_parse_chunk_overlap: number;
    semantic_chunk_parse_embedding_model: number | null;
    chunk_type: string;
  }): Promise<any[]> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/preview_chunk/', params);
  };

  const getDocListConfig = async (params: any) => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/get_doc_list_config/', params);
  };

  /**
   * Fetches configuration for a single document by ID.
   */
  const getDocumentConfig = async (id: number): Promise<any> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_document/${id}/`);
  };

  /**
   * Fetches tasks assigned to the current user.
   */
  const fetchMyTasks = async (params: any): Promise<any[]> => {
    return get('/opspilot/knowledge_mgmt/knowledge_document/get_my_tasks/',  { params });
  };

  /**
   * Fetches QA pairs task status for a specific document.
   */
  const fetchQAPairsTaskStatus = async (params: { document_id: string }): Promise<any[]> => {
    return get('/opspilot/knowledge_mgmt/qa_pairs/get_qa_pairs_task_status/', { params });
  };

  /**
   * Fetches QA pairs for the knowledge base.
   */
  const fetchQAPairs = async (params: any): Promise<any> => {
    return get('/opspilot/knowledge_mgmt/qa_pairs/', { params });
  };

  /**
   * Deletes a single QA pair.
   */
  const deleteQAPair = async (qaPairId: number): Promise<void> => {
    return del(`/opspilot/knowledge_mgmt/qa_pairs/${qaPairId}/`);
  };

  const createOneQAPair = async (payload: {
    knowledge_id: number;
    qa_pairs_id: number;
    question: string;
    answer: string;
  }): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/create_one_qa_pairs/', payload);
  };

  /**
   * Creates QA pairs from selected documents.
   */
  const createQAPairs = async (payload: {
    knowledge_base_id: number;
    llm_model_id: number;
    qa_count: number;
    document_list: Array<{
      name: string;
      document_id: number;
      document_source: string;
    }>;
  }): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/create_qa_pairs/', payload);
  };

  const updateQAPair = async (payload: {
    qa_pairs_id: number;
    id: string;
    question: string;
    answer: string;
  }): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/update_qa_pairs/', payload);
  };

  const deleteOneQAPair = async (payload: {
    qa_pairs_id: number;
    id: string;
  }): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/delete_one_qa_pairs/', payload);
  };

  /**
   * Creates custom QA pairs manually.
   */
  const createCustomQAPairs = async (payload: {
    knowledge_base_id: number;
    name: string;
    qa_pairs: Array<{
      question: string;
      answer: string;
    }>;
  }): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/create_qa_pairs_by_custom/', payload);
  };

  /**
   * Creates QA pairs from selected chunks.
   */
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
  }): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/create_qa_pairs_by_chunk/', payload);
  };

  /**
   * Fetches QA pairs chunk details for a specific QA pair.
   */
  const fetchQAPairDetails = async (params: {
    qa_pair_id: number;
    page?: number;
    page_size?: number;
    search_text?: string;
  }): Promise<any> => {
    return get(`/opspilot/knowledge_mgmt/qa_pairs/${params.qa_pair_id}/get_details/`, { params });
  };

  /**
   * Fetches QA pairs for a specific chunk.
   */
  const fetchChunkQAPairs = async (indexName: string, chunkId: string, knowledgeBaseId: number | undefined): Promise<any> => {
    return get('/opspilot/knowledge_mgmt/qa_pairs/get_chunk_qa_pairs/', {
      params: {
        index_name: indexName,
        chunk_id: chunkId,
        knowledge_base_id: knowledgeBaseId
      },
    });
  };

  const fetchKnowledgeGraphDetails = async (knowledgeBaseId: number): Promise<{
    graph_id?: number;
    is_exists: boolean;
    graph?: any;
    status?: string;
  }> => {
    return get('/opspilot/knowledge_mgmt/knowledge_graph/get_details/', {
      params: {
        knowledge_base_id: knowledgeBaseId,
      },
    });
  };

  const fetchKnowledgeGraphById = async (graphId: number): Promise<{
    knowledge_base: number;
    llm_model: number;
    rerank_model: number;
    embed_model: number;
    rebuild_community: boolean;
    doc_list: Array<{
      id: number;
      source: string;
    }>;
  }> => {
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
  }): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/knowledge_graph/', payload);
  };

  /**
   * Updates existing knowledge graph configuration.
   */
  const updateKnowledgeGraph = async (graphId: number, payload: {
    knowledge_base: number;
    llm_model: number;
    rerank_model: number;
    embed_model: number;
    doc_list: Array<{
      id: number;
      source: string;
    }>;
  }): Promise<any> => {
    return patch(`/opspilot/knowledge_mgmt/knowledge_graph/${graphId}/`, payload);
  };

  /**
   * Rebuilds knowledge graph community.
   */
  const rebuildKnowledgeGraphCommunity = async (knowledgeBaseId: number): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/knowledge_graph/rebuild_graph_community/', {
      knowledge_base_id: knowledgeBaseId,
    });
  };

  /**
   * import_qa_json
   */
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
  ): Promise<any> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_document/get_chunk_detail/`, { 
      params: {
        knowledge_id,
        chunk_id,
        type,
      },
    });
  };

  /**
   * Deletes chunks from knowledge documents.
   */
  const deleteChunks = async (payload: {
    knowledge_base_id: number;
    ids: string[];
    delete_all: boolean;
  }): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/delete_chunks/', payload);
  };

  /**
   * Generates questions from documents.
   */
  const generateQuestions = async (payload: {
    document_list: Array<{ document_id: number }>;
    knowledge_base_id: number;
    llm_model_id: number;
    question_prompt: string;
  }): Promise<Array<{
    question: string;
    content: string;
  }>> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/generate_question/', payload);
  };

  /**
   * Generates answers for questions.
   */
  const generateAnswers = async (payload: {
    answer_llm_model_id: number;
    answer_prompt: string;
    knowledge_base_id: number;
    question_data: Array<{
      question: string;
      content: string;
    }>;
  }): Promise<Array<{
    answer: string;
    question: string;
  }>> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/generate_answer/', payload);
  };

  /**
   * Generates answers to ES for QA pairs.
   */
  const generateAnswerToEs = async (payload: {
    qa_pairs_id: number;
  }): Promise<any> => {
    return post('/opspilot/knowledge_mgmt/qa_pairs/generate_answer_to_es/', payload);
  };

  /**
   * Fetches QA pair detail by ID.
   */
  const getQAPairDetail = async (qaPairId: number): Promise<{
    id: number;
    name: string;
    llm_model: number;
    answer_llm_model: number;
    qa_count: number;
    question_prompt: string;
    answer_prompt: string;
    document_id: number;
    document_source: string;
  }> => {
    return get(`/opspilot/knowledge_mgmt/qa_pairs/${qaPairId}/`);
  };

  /**
   * Updates QA pair configuration.
   */
  const updateQAPairConfig = async (qaPairId: number, payload: {
    llm_model_id: number;
    qa_count: number;
    question_prompt: string;
    answer_prompt: string;
    answer_llm_model_id: number;
    only_question?: boolean;
  }): Promise<any> => {
    return patch(`/opspilot/knowledge_mgmt/qa_pairs/${qaPairId}/`, payload);
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
  };
};
