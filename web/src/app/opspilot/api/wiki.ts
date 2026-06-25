import useApiClient from '@/utils/request';
import { LlmModel } from '@/app/opspilot/types/skill';
import {
  BuildRecord,
  CheckItem,
  KnowledgePage,
  Material,
  MaterialInfo,
  PageVersion,
  PurposeSchemaResult,
  PurposeSchemaTemplate,
  WikiGraph,
  WikiKnowledgeBase,
  WikiOverview,
  WikiQaResult,
  WikiSearchHit,
} from '@/app/opspilot/types/wiki';

const BASE = '/opspilot/wiki_mgmt';

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

  const buildContext = (kb_ids: number[], query: string, top_k = 5): Promise<unknown> =>
    post(`${BASE}/knowledge_base/context/`, { kb_ids, query, top_k });

  const rebuildKnowledgeBase = (id: number): Promise<BuildRecord> => post(`${BASE}/knowledge_base/${id}/rebuild/`, {});

  // ---- 资料 ----
  const fetchMaterials = (kbId: number, params?: Record<string, unknown>): Promise<Material[]> =>
    get(`${BASE}/material/`, { params: { ...params, knowledge_base: kbId } });

  const fetchMaterial = (id: number): Promise<Material> => get(`${BASE}/material/${id}/`);

  const fetchMaterialInfo = (id: number): Promise<MaterialInfo> => get(`${BASE}/material/${id}/info/`);

  const createMaterial = (data: Partial<Material>): Promise<Material> => post(`${BASE}/material/`, data);

  const createMaterialFile = (kbId: number, name: string, file: File): Promise<Material> => {
    const fd = new FormData();
    fd.append('knowledge_base', String(kbId));
    fd.append('name', name);
    fd.append('material_type', 'file');
    fd.append('file', file);
    return post(`${BASE}/material/`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
  };

  const deleteMaterial = (id: number): Promise<{ pending_review: number }> => del(`${BASE}/material/${id}/`);

  const ingestMaterial = (id: number): Promise<Material> => post(`${BASE}/material/${id}/ingest/`, {});

  const buildMaterial = (id: number, async = false): Promise<BuildRecord | { async: boolean }> =>
    post(`${BASE}/material/${id}/build/`, { async });

  const proposeUpdate = (id: number): Promise<BuildRecord> => post(`${BASE}/material/${id}/propose_update/`, {});

  // ---- 页面 ----
  const fetchPages = (kbId: number, params?: Record<string, unknown>): Promise<KnowledgePage[]> =>
    get(`${BASE}/page/`, { params: { ...params, knowledge_base: kbId } });

  const fetchPage = (id: number): Promise<KnowledgePage> => get(`${BASE}/page/${id}/`);

  const createPage = (data: Partial<KnowledgePage> & { body?: string }): Promise<KnowledgePage> =>
    post(`${BASE}/page/`, data);

  const updatePage = (id: number, data: Partial<KnowledgePage> & { body?: string }): Promise<KnowledgePage> =>
    put(`${BASE}/page/${id}/`, data);

  const deletePage = (id: number): Promise<void> => del(`${BASE}/page/${id}/`);

  const fetchPageVersions = (id: number): Promise<PageVersion[]> => get(`${BASE}/page/${id}/versions/`);

  const restorePageVersion = (id: number, version_id: number): Promise<KnowledgePage> =>
    post(`${BASE}/page/${id}/restore/`, { version_id });

  const fetchPageDiff = (id: number, from: number, to: number): Promise<{ diff: string[] }> =>
    get(`${BASE}/page/${id}/diff/`, { params: { from, to } });

  // ---- 构建记录 ----
  const fetchBuildRecords = (kbId: number, params?: Record<string, unknown>): Promise<BuildRecord[]> =>
    get(`${BASE}/build_record/`, { params: { ...params, knowledge_base: kbId } });

  const fetchBuildRecord = (id: number): Promise<BuildRecord> => get(`${BASE}/build_record/${id}/`);

  const retryBuild = (id: number): Promise<{ async: boolean }> => post(`${BASE}/build_record/${id}/retry/`, {});

  const cancelBuild = (id: number): Promise<BuildRecord> => post(`${BASE}/build_record/${id}/cancel/`, {});

  // ---- 检查项 ----
  const fetchCheckItems = (
    kbId: number,
    params?: Record<string, unknown>
  ): Promise<CheckItem[]> => get(`${BASE}/check_item/`, { params: { ...params, knowledge_base: kbId } });

  const acceptCheck = (id: number): Promise<unknown> => post(`${BASE}/check_item/${id}/accept/`, {});

  const rejectCheck = (id: number): Promise<unknown> => post(`${BASE}/check_item/${id}/reject/`, {});

  return {
    fetchKnowledgeBases,
    fetchKnowledgeBase,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    fetchTemplates,
    fetchLlmModels,
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
    rebuildKnowledgeBase,
    fetchMaterials,
    fetchMaterial,
    fetchMaterialInfo,
    createMaterial,
    createMaterialFile,
    deleteMaterial,
    ingestMaterial,
    buildMaterial,
    proposeUpdate,
    fetchPages,
    fetchPage,
    createPage,
    updatePage,
    deletePage,
    fetchPageVersions,
    restorePageVersion,
    fetchPageDiff,
    fetchBuildRecords,
    fetchBuildRecord,
    retryBuild,
    cancelBuild,
    fetchCheckItems,
    acceptCheck,
    rejectCheck,
  };
};

export default useWikiApi;
