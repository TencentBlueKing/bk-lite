import useApiClient from '@/utils/request';
import { LlmModel } from '@/app/opspilot/types/skill';
import { Model } from '@/app/opspilot/types/provider';
import {
  BuildMaintenanceBatchRetryResult,
  BuildRecord,
  CheckItem,
  CheckDecisionRequest,
  CheckDecisionResponse,
  FetchDecisionItemsParams,
  RevokeDecisionRuleRequest,
  RevokeDecisionRuleResponse,
  KnowledgePage,
  MarkdownImportResult,
  Material,
  MaterialBatchCreateResult,
  MaterialDeleteImpact,
  MaterialInfo,
  MaterialUpdateImpact,
  PageVersion,
  PurposeSchemaResult,
  PurposeSchemaTemplate,
  SaveAnswerPageInput,
  SaveAnswerPageResult,
  WikiContextOptions,
  WikiContextResult,
  WikiGraph,
  WikiKnowledgeBase,
  WikiOverview,
  WikiPageSourcesResult,
  WikiPreviewMergeResult,
  WikiQaResult,
  WikiSearchHit,
} from '@/app/opspilot/types/wiki';

const BASE = '/opspilot/wiki_mgmt';

// 后端列表统一返回的分页结构 {count, items}
export interface Paged<T> {
  count: number;
  items: T[];
}

export const useWikiApi = () => {
  const { get, post, put, del } = useApiClient();

  // ---- 知识库 ----
  // 后端列表返回分页对象 {count, items};归一化为数组(兼容直接返回数组),避免调用方对对象做 .map 崩溃
  const fetchKnowledgeBases = async (params?: Record<string, unknown>): Promise<WikiKnowledgeBase[]> => {
    const res = await get(`${BASE}/knowledge_base/`, { params });
    return Array.isArray(res) ? res : ((res as { items?: WikiKnowledgeBase[] })?.items ?? []);
  };

  const fetchKnowledgeBase = (id: number): Promise<WikiKnowledgeBase> => get(`${BASE}/knowledge_base/${id}/`);

  const createKnowledgeBase = (data: Partial<WikiKnowledgeBase>): Promise<WikiKnowledgeBase> =>
    post(`${BASE}/knowledge_base/`, data);

  const updateKnowledgeBase = (id: number, data: Partial<WikiKnowledgeBase>): Promise<WikiKnowledgeBase> =>
    put(`${BASE}/knowledge_base/${id}/`, data);

  const deleteKnowledgeBase = (id: number): Promise<void> => del(`${BASE}/knowledge_base/${id}/`);

  const fetchTemplates = (): Promise<PurposeSchemaTemplate[]> => get(`${BASE}/knowledge_base/templates/`);

  // 知识库需绑定 LLM 模型用于"资料摘要"与"页面构建"。
  // 注意:/llm/ 是「LLM 技能/Bot」列表,真正的「模型」在 /llm_model/(与技能配置页一致)
  const fetchLlmModels = (): Promise<LlmModel[]> =>
    get('/opspilot/model_provider_mgmt/llm_model/', { params: { enabled: 1 } });

  // EmbedProvider 用于 Wiki 语义索引/语义检索,管理入口同模型供应商页的"向量模型"。
  const fetchEmbedProviders = (): Promise<Model[]> =>
    get('/opspilot/model_provider_mgmt/embed_provider/', { params: { enabled: 1 } });

  const generatePurposeSchema = (data: {
    template_key?: string;
    description?: string;
    llm_model_id?: number;
  }): Promise<PurposeSchemaResult> => post(`${BASE}/knowledge_base/generate_purpose_schema/`, data);

  const search = (id: number, query: string, top_k = 5): Promise<WikiSearchHit[]> =>
    post(`${BASE}/knowledge_base/${id}/search/`, { query, top_k });

  const qa = (id: number, query: string): Promise<WikiQaResult> => post(`${BASE}/knowledge_base/${id}/qa/`, { query });

  const scan = (id: number): Promise<{ created: number }> => post(`${BASE}/knowledge_base/${id}/scan/`, {});

  const fetchRelations = (id: number): Promise<unknown[]> => get(`${BASE}/knowledge_base/${id}/relations/`);

  const rebuildRelations = (id: number): Promise<{ relations: number }> =>
    post(`${BASE}/knowledge_base/${id}/rebuild_relations/`, {});

  const fetchGraph = (id: number): Promise<WikiGraph> => get(`${BASE}/knowledge_base/${id}/graph/`);

  const fetchGraphAnalysis = (id: number): Promise<WikiGraph> => get(`${BASE}/knowledge_base/${id}/graph_analysis/`);

  const fetchOverview = (id: number): Promise<WikiOverview> => get(`${BASE}/knowledge_base/${id}/overview/`);

  const buildContext = (kb_ids: number[], query: string, options: WikiContextOptions = {}): Promise<WikiContextResult> =>
    post(`${BASE}/knowledge_base/context/`, {
      kb_ids,
      query,
      top_k: options.top_k ?? 5,
      token_budget: options.token_budget,
      graph_hops: options.graph_hops,
      retrieval_mode: options.retrieval_mode,
    });

  const reindexKnowledgeBase = (id: number): Promise<BuildRecord> =>
    post(`${BASE}/knowledge_base/${id}/reindex/`, {});

  const exportKnowledgeBaseMarkdown = (id: number): Promise<Blob> =>
    get(`${BASE}/knowledge_base/${id}/export_markdown/`, { responseType: 'blob' });

  const previewMergeKnowledgeBase = (id: number): Promise<WikiPreviewMergeResult> =>
    get(`${BASE}/knowledge_base/${id}/preview_merge/`);

  const importKnowledgeBaseMarkdown = (id: number, file: File): Promise<MarkdownImportResult> => {
    const fd = new FormData();
    fd.append('file', file);
    return post(`${BASE}/knowledge_base/${id}/import_markdown/`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
  };

  const rebuildKnowledgeBase = (id: number): Promise<BuildRecord> => post(`${BASE}/knowledge_base/${id}/rebuild/`, {});

  // ---- 资料 ----
  const fetchMaterials = (kbId: number, params?: Record<string, unknown>): Promise<Paged<Material>> =>
    get(`${BASE}/material/`, { params: { ...params, knowledge_base: kbId } });

  const fetchMaterial = (id: number): Promise<Material> => get(`${BASE}/material/${id}/`);

  const fetchMaterialInfo = (id: number): Promise<MaterialInfo> => get(`${BASE}/material/${id}/info/`);

  const fetchMaterialDeleteImpact = (id: number): Promise<MaterialDeleteImpact> =>
    get(`${BASE}/material/${id}/delete_impact/`);

  const fetchMaterialUpdateImpact = (id: number): Promise<MaterialUpdateImpact> =>
    get(`${BASE}/material/${id}/update_impact/`);

  const createMaterial = (data: Partial<Material>): Promise<Material> => post(`${BASE}/material/`, data);
  const updateMaterial = (id: number, data: Partial<Material>): Promise<Material> =>
    put(`${BASE}/material/${id}/`, data);

  const createMaterialFile = (kbId: number, name: string, file: File, ocrEnhance = false): Promise<Material> => {
    const fd = new FormData();
    fd.append('knowledge_base', String(kbId));
    fd.append('name', name);
    fd.append('material_type', 'file');
    fd.append('file', file);
    fd.append('ocr_enhance', String(ocrEnhance));
    return post(`${BASE}/material/`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
  };

  const batchCreateMaterials = (
    kbId: number,
    files: File[],
    ocrEnhance = false
  ): Promise<MaterialBatchCreateResult> => {
    const fd = new FormData();
    fd.append('knowledge_base', String(kbId));
    fd.append('ocr_enhance', String(ocrEnhance));
    files.forEach((file) => fd.append('files', file));
    return post(`${BASE}/material/batch_create/`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  };

  const deleteMaterial = (id: number): Promise<{ pending_review: number }> => del(`${BASE}/material/${id}/`);

  const ingestMaterial = (id: number): Promise<Material> => post(`${BASE}/material/${id}/ingest/`, {});

  const buildMaterial = (id: number, async = false): Promise<BuildRecord | { async: boolean }> =>
    post(`${BASE}/material/${id}/build/`, { async });

  const proposeUpdate = (id: number): Promise<BuildRecord> => post(`${BASE}/material/${id}/propose_update/`, {});

  const reindexMaterial = (id: number): Promise<BuildRecord> => post(`${BASE}/material/${id}/reindex/`, {});

  // ---- 页面 ----
  const fetchPages = (kbId: number, params?: Record<string, unknown>): Promise<Paged<KnowledgePage>> =>
    get(`${BASE}/page/`, { params: { ...params, knowledge_base: kbId } });

  const fetchPage = (id: number): Promise<KnowledgePage> => get(`${BASE}/page/${id}/`);

  const fetchPageSources = (id: number): Promise<WikiPageSourcesResult> => get(`${BASE}/page/${id}/sources/`);

  const createPage = (data: Partial<KnowledgePage> & { body?: string }): Promise<KnowledgePage> =>
    post(`${BASE}/page/`, data);

  const saveAnswerPage = (data: SaveAnswerPageInput): Promise<SaveAnswerPageResult> =>
    post(`${BASE}/page/save_answer/`, data);

  const updatePage = (id: number, data: Partial<KnowledgePage> & { body?: string }): Promise<KnowledgePage> =>
    put(`${BASE}/page/${id}/`, data);

  const deletePage = (id: number): Promise<void> => del(`${BASE}/page/${id}/`);

  const batchDeletePages = (
    kbId: number,
    ids: number[]
  ): Promise<{ deleted: number; skipped: number; skipped_ids: number[] }> =>
    post(`${BASE}/page/batch_delete/`, { knowledge_base: kbId, ids });

  const reindexPage = (id: number): Promise<BuildRecord> => post(`${BASE}/page/${id}/reindex/`, {});

  const fetchPageVersions = (id: number): Promise<PageVersion[]> => get(`${BASE}/page/${id}/versions/`);

  const restorePageVersion = (id: number, version_id: number): Promise<KnowledgePage> =>
    post(`${BASE}/page/${id}/restore/`, { version_id });

  const restorePageFromArchive = (id: number): Promise<KnowledgePage> =>
    post(`${BASE}/page/${id}/restore_from_archive/`, {});

  const fetchPageDiff = (id: number, from: number, to: number): Promise<{ diff: string[] }> =>
    get(`${BASE}/page/${id}/diff/`, { params: { from, to } });

  // ---- 构建记录 ----
  const fetchBuildRecords = (kbId: number, params?: Record<string, unknown>): Promise<Paged<BuildRecord>> =>
    get(`${BASE}/build_record/`, { params: { ...params, knowledge_base: kbId } });

  const fetchBuildRecord = (id: number): Promise<BuildRecord> => get(`${BASE}/build_record/${id}/`);

  const retryBuild = (id: number): Promise<{ async: boolean }> => post(`${BASE}/build_record/${id}/retry/`, {});

  const retryBuildMaintenance = (id: number, stages?: string[]): Promise<BuildRecord> =>
    post(`${BASE}/build_record/${id}/retry_maintenance/`, stages ? { stages } : {});

  const batchRetryBuildMaintenance = (
    kbId: number,
    ids: number[],
    stages?: string[]
  ): Promise<BuildMaintenanceBatchRetryResult> =>
    post(`${BASE}/build_record/batch_retry_maintenance/`, stages ? { knowledge_base: kbId, ids, stages } : { knowledge_base: kbId, ids });

  const cancelBuild = (id: number): Promise<BuildRecord> => post(`${BASE}/build_record/${id}/cancel/`, {});

  // ---- 检查项 ----
  const fetchCheckItems = (
    kbId: number,
    params?: Record<string, unknown>
  ): Promise<Paged<CheckItem>> => get(`${BASE}/check_item/`, { params: { ...params, knowledge_base: kbId } });

  const fetchDecisionItems = (
    kbId: number,
    params: FetchDecisionItemsParams
  ): Promise<Paged<CheckItem>> =>
    fetchCheckItems(kbId, { ...params, decision_only: true, view: params.view });

  const decideCheck = (id: number, payload: CheckDecisionRequest): Promise<CheckDecisionResponse> =>
    post(`${BASE}/check_item/${id}/decide/`, payload);

  const revokeDecisionRule = (
    id: number,
    payload: RevokeDecisionRuleRequest = {}
  ): Promise<RevokeDecisionRuleResponse> =>
    post(`${BASE}/check_item/${id}/revoke_rule/`, payload);

  const assignCheck = (
    id: number,
    payload: { assignee?: string; due_at?: string | null; action_type?: string }
  ): Promise<CheckItem> => post(`${BASE}/check_item/${id}/assign/`, payload);

  return {
    fetchKnowledgeBases,
    fetchKnowledgeBase,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    fetchTemplates,
    fetchLlmModels,
    fetchEmbedProviders,
    generatePurposeSchema,
    search,
    qa,
    scan,
    fetchRelations,
    rebuildRelations,
    fetchGraph,
    fetchGraphAnalysis,
    fetchOverview,
    buildContext,
    reindexKnowledgeBase,
    exportKnowledgeBaseMarkdown,
    importKnowledgeBaseMarkdown,
    previewMergeKnowledgeBase,
    rebuildKnowledgeBase,
    fetchMaterials,
    fetchMaterial,
    fetchMaterialInfo,
    fetchMaterialDeleteImpact,
    fetchMaterialUpdateImpact,
    createMaterial,
    updateMaterial,
    createMaterialFile,
    batchCreateMaterials,
    deleteMaterial,
    ingestMaterial,
    buildMaterial,
    proposeUpdate,
    reindexMaterial,
    fetchPages,
    fetchPage,
    fetchPageSources,
    createPage,
    saveAnswerPage,
    updatePage,
    deletePage,
    batchDeletePages,
    reindexPage,
    fetchPageVersions,
    restorePageVersion,
    restorePageFromArchive,
    fetchPageDiff,
    fetchBuildRecords,
    fetchBuildRecord,
    retryBuild,
    retryBuildMaintenance,
    batchRetryBuildMaintenance,
    cancelBuild,
    fetchCheckItems,
    fetchDecisionItems,
    decideCheck,
    revokeDecisionRule,
    assignCheck,
  };
};

export default useWikiApi;
