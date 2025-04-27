import useApiClient from '@/utils/request';
import { KnowledgeValues } from '@/app/opspilot/types/knowledge';
import { ResultItem } from '@/app/opspilot/types/global';

export const useKnowledgeApi = () => {
  const { get, post, patch, del } = useApiClient();

  /**
   * Fetches embedding models.
   */
  const fetchEmbeddingModels = async (): Promise<any[]> => {
    return get('/opspilot/model_provider_mgmt/embed_provider/');
  };

  /**
   * Fetches the knowledge base.
   */
  const fetchKnowledgeBase = async (): Promise<any[]> => {
    return get('/opspilot/knowledge_mgmt/knowledge_base/');
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
  const batchTrainDocuments = async (docIds: React.Key[]): Promise<void> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/batch_train/', {
      knowledge_document_ids: docIds,
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
    return get('/opspilot/model_provider_mgmt/rerank_provider/');
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
  const testKnowledge = async (params: any): Promise<ResultItem[]> => {
    return post('/opspilot/knowledge_mgmt/knowledge_document/testing', params);
  };

  /**
   * Fetches knowledge base details by ID.
   */
  const fetchKnowledgeBaseDetails = async (id: number): Promise<{ name: string; introduction: string }> => {
    return get(`/opspilot/knowledge_mgmt/knowledge_base/${id}`);
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
  };
};
