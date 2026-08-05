import useApiClient from "@/utils/request";
import { LlmModel } from "@/app/opspilot/types/skill";
import { Model } from "@/app/opspilot/types/provider";
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
  Material,
  MaterialBatchCreateResult,
  MaterialBatchUploadEntry,
  MaterialDeleteImpact,
  MaterialFileUploadMetadata,
  MaterialInfo,
  MaterialUpdateImpact,
  WikiMarkdownImportExecuteResult,
  WikiMarkdownImportPreflightOptions,
  WikiMarkdownImportPreflightResult,
  PageVersion,
  PurposeSchemaResult,
  PurposeSchemaTemplate,
  SaveAnswerPageInput,
  SaveAnswerPageResult,
  WikiContextOptions,
  WikiContextResult,
  WikiDirectoryEnableResult,
  WikiDirectoryTreeResult,
  WikiDirectoryOperationExecuteRequest,
  WikiDirectoryOperationExecuteResult,
  WikiDirectoryOperationPreview,
  WikiDirectoryOperationRequest,
  WikiStructureReadResult,
  WikiStructureSaveRequest,
  WikiStructureSaveResponse,
  WikiGenerationRollbackExecuteRequest,
  WikiGenerationRollbackExecuteResult,
  WikiGenerationRollbackPreview,
  WikiGenerationRollbackRequest,
  WikiGraph,
  WikiKnowledgeBase,
  WikiOverview,
  WikiPageBatchDeleteResult,
  WikiPageDeleteResult,
  WikiPageDirectoryMutationResult,
  WikiPageRestoreFromArchiveResult,
  WikiPageSourcesResult,
  WikiPreviewMergeResult,
  WikiQaResult,
  WikiQaStreamDone,
  WikiQaStreamError,
  WikiQaStreamHandlers,
  WikiQaStreamMeta,
  WikiSearchHit,
} from "@/app/opspilot/types/wiki";
import {
  applyWikiMediaDisplayUrls,
  collectBareWikiMediaLocators,
  collectWikiMediaLocators,
  isWikiMediaDisplayUrl,
} from "@/app/opspilot/utils/wikiMediaDisplay";
import { useAuth } from "@/context/auth";
import { useSession } from "next-auth/react";
import { resolveAuthToken } from "@/utils/authRecovery";

const BASE = "/opspilot/wiki_mgmt";

// 后端列表统一返回的分页结构 {count, items}
export interface Paged<T> {
  count: number;
  items: T[];
}

export interface WikiGraphQueryParams {
  directory_id?: number;
  include_descendants?: boolean;
}

export const useWikiApi = () => {
  const { get, post, put, del } = useApiClient();
  const authContext = useAuth();
  const { data: session } = useSession();
  const token = resolveAuthToken(authContext?.token, (session?.user as any)?.token);

  // ---- 知识库 ----
  // 后端列表返回分页对象 {count, items};归一化为数组(兼容直接返回数组),避免调用方对对象做 .map 崩溃
  const fetchKnowledgeBases = async (
    params?: Record<string, unknown>,
  ): Promise<WikiKnowledgeBase[]> => {
    const res = await get(`${BASE}/knowledge_base/`, { params });
    return Array.isArray(res)
      ? res
      : ((res as { items?: WikiKnowledgeBase[] })?.items ?? []);
  };

  const fetchKnowledgeBase = (id: number): Promise<WikiKnowledgeBase> =>
    get(`${BASE}/knowledge_base/${id}/`);

  const enableDirectoryGovernance = (
    id: number,
  ): Promise<WikiDirectoryEnableResult> =>
    post(`${BASE}/knowledge_base/${id}/directory_enable/`, {});

  const createKnowledgeBase = (
    data: Partial<WikiKnowledgeBase>,
  ): Promise<WikiKnowledgeBase> => post(`${BASE}/knowledge_base/`, data);

  const updateKnowledgeBase = (
    id: number,
    data: Partial<WikiKnowledgeBase>,
  ): Promise<WikiKnowledgeBase> => put(`${BASE}/knowledge_base/${id}/`, data);

  const deleteKnowledgeBase = (id: number): Promise<void> =>
    del(`${BASE}/knowledge_base/${id}/`);

  const fetchTemplates = (): Promise<PurposeSchemaTemplate[]> =>
    get(`${BASE}/knowledge_base/templates/`);

  // 知识库需绑定 LLM 模型用于"资料摘要"与"页面构建"。
  // 注意:/llm/ 是「LLM 技能/Bot」列表,真正的「模型」在 /llm_model/(与技能配置页一致)
  const fetchLlmModels = (): Promise<LlmModel[]> =>
    get("/opspilot/model_provider_mgmt/llm_model/", { params: { enabled: 1 } });

  // EmbedProvider 用于 Wiki 语义索引/语义检索,管理入口同模型供应商页的"向量模型"。
  const fetchEmbedProviders = (): Promise<Model[]> =>
    get("/opspilot/model_provider_mgmt/embed_provider/", {
      params: { enabled: 1 },
    });

  const generatePurposeSchema = (data: {
    template_key?: string;
    description?: string;
    llm_model_id?: number;
  }): Promise<PurposeSchemaResult> =>
    post(`${BASE}/knowledge_base/generate_purpose_schema/`, data);

  const search = (
    id: number,
    query: string,
    top_k = 5,
  ): Promise<WikiSearchHit[]> =>
    post(`${BASE}/knowledge_base/${id}/search/`, { query, top_k });

  const qa = (id: number, query: string): Promise<WikiQaResult> =>
    post(`${BASE}/knowledge_base/${id}/qa/`, { query });

  const qaStream = async (
    id: number,
    query: string,
    handlers: WikiQaStreamHandlers = {},
    options?: { signal?: AbortSignal },
  ): Promise<void> => {
    if (!token) {
      throw new Error("No token available");
    }
    const response = await fetch(
      `/api/proxy${BASE}/knowledge_base/${id}/qa_stream/`,
      {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        credentials: "include",
        body: JSON.stringify({ query }),
        signal: options?.signal,
      },
    );
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("Failed to get response reader");
    }
    const decoder = new TextDecoder();
    let buffer = "";
    let sawDone = false;

    const dispatch = (payload: Record<string, unknown>) => {
      const event = String(payload.event || "");
      if (event === "meta") {
        handlers.onMeta?.(payload as unknown as WikiQaStreamMeta);
        return;
      }
      if (event === "delta") {
        handlers.onDelta?.(String(payload.text || ""));
        return;
      }
      if (event === "done") {
        sawDone = true;
        handlers.onDone?.(payload as unknown as WikiQaStreamDone);
        return;
      }
      if (event === "error") {
        handlers.onError?.(payload as unknown as WikiQaStreamError);
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith("data:")) continue;
        const dataStr = trimmed.slice(5).trim();
        if (!dataStr || dataStr === "[DONE]") continue;
        try {
          dispatch(JSON.parse(dataStr) as Record<string, unknown>);
        } catch {
          // ignore malformed SSE chunks
        }
      }
    }

    const trailing = buffer.trim();
    if (trailing.startsWith("data:")) {
      const dataStr = trailing.slice(5).trim();
      if (dataStr && dataStr !== "[DONE]") {
        try {
          dispatch(JSON.parse(dataStr) as Record<string, unknown>);
        } catch {
          // ignore
        }
      }
    }

    if (!sawDone) {
      handlers.onError?.({
        event: "error",
        message: "stream ended without done event",
        code: "wiki_qa_stream_incomplete",
      });
    }
  };

  const scan = (id: number): Promise<{ created: number }> =>
    post(`${BASE}/knowledge_base/${id}/scan/`, {});

  const fetchRelations = (id: number): Promise<unknown[]> =>
    get(`${BASE}/knowledge_base/${id}/relations/`);

  const rebuildRelations = (id: number): Promise<{ relations: number }> =>
    post(`${BASE}/knowledge_base/${id}/rebuild_relations/`, {});

  const fetchGraph = (
    id: number,
    params?: WikiGraphQueryParams,
  ): Promise<WikiGraph> =>
    get(`${BASE}/knowledge_base/${id}/graph/`, { params });

  const fetchGraphAnalysis = (
    id: number,
    params?: WikiGraphQueryParams,
  ): Promise<WikiGraph> =>
    get(`${BASE}/knowledge_base/${id}/graph_analysis/`, { params });

  const fetchOverview = (id: number): Promise<WikiOverview> =>
    get(`${BASE}/knowledge_base/${id}/overview/`);

  const buildContext = (
    kb_ids: number[],
    query: string,
    options: WikiContextOptions = {},
  ): Promise<WikiContextResult> =>
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
    get(`${BASE}/knowledge_base/${id}/export_markdown/`, {
      responseType: "blob",
    });

  const previewMergeKnowledgeBase = (
    id: number,
  ): Promise<WikiPreviewMergeResult> =>
    get(`${BASE}/knowledge_base/${id}/preview_merge/`);

  const preflightKnowledgeBaseMarkdown = (
    id: number,
    file: File,
    options: WikiMarkdownImportPreflightOptions = {},
  ): Promise<WikiMarkdownImportPreflightResult> => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("options", JSON.stringify(options));
    return post(`${BASE}/knowledge_base/${id}/import_markdown_preflight/`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  };

  const executeKnowledgeBaseMarkdown = (
    id: number,
    file: File,
    token: string,
  ): Promise<WikiMarkdownImportExecuteResult> => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("token", token);
    return post(`${BASE}/knowledge_base/${id}/import_markdown_execute/`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  };

  const previewGenerationRollback = (
    id: number,
    payload: WikiGenerationRollbackRequest,
  ): Promise<WikiGenerationRollbackPreview> =>
    post(`${BASE}/knowledge_base/${id}/rollback_preview/`, payload);

  const executeGenerationRollback = (
    id: number,
    payload: WikiGenerationRollbackExecuteRequest,
  ): Promise<WikiGenerationRollbackExecuteResult> =>
    post(`${BASE}/knowledge_base/${id}/rollback_execute/`, payload);

  const rebuildKnowledgeBase = (id: number): Promise<BuildRecord> =>
    post(`${BASE}/knowledge_base/${id}/rebuild/`, {});

  // ---- 资料 ----
  const fetchMaterials = (
    kbId: number,
    params?: Record<string, unknown>,
  ): Promise<Paged<Material>> =>
    get(`${BASE}/material/`, { params: { ...params, knowledge_base: kbId } });

  const fetchMaterial = (id: number): Promise<Material> =>
    get(`${BASE}/material/${id}/`);

  const rewriteMarkdownMediaUrls = async (
    markdown: string,
    sign: (locators: string[]) => Promise<Record<string, string>>,
  ): Promise<string> => {
    // 含 MinIO 预签名内的 locator 也重签，统一升级为同源 /api/proxy 展示 URL
    const locators = collectWikiMediaLocators(markdown);
    if (!locators.length) return markdown;
    try {
      const urls = await sign(locators);
      const usable: Record<string, string> = {};
      for (const loc of locators) {
        const url = (urls[loc] || "").trim();
        if (url && url !== loc && isWikiMediaDisplayUrl(url)) {
          usable[loc] = url;
        }
      }
      if (!Object.keys(usable).length) return markdown;
      const next = applyWikiMediaDisplayUrls(markdown, usable);
      const stillBare = collectBareWikiMediaLocators(next);
      if (stillBare.length) {
        console.warn("[wiki] media rewrite incomplete", stillBare);
      }
      return next;
    } catch {
      return markdown;
    }
  };

  const fetchMaterialInfo = async (id: number): Promise<MaterialInfo> => {
    const info = (await get(`${BASE}/material/${id}/info/`)) as MaterialInfo;
    const sign = async (locators: string[]) => {
      const signed = (await post(`${BASE}/material/${id}/sign_media/`, {
        locators,
      })) as { urls?: Record<string, string> };
      return signed?.urls || {};
    };
    // parsed_markdown 与 ai_summary 都可能含 wiki/media，需一并改写
    const [parsed_markdown, ai_summary] = await Promise.all([
      rewriteMarkdownMediaUrls(info?.parsed_markdown || "", sign),
      rewriteMarkdownMediaUrls(info?.ai_summary || "", sign),
    ]);
    if (
      parsed_markdown === (info?.parsed_markdown || "") &&
      ai_summary === (info?.ai_summary || "")
    ) {
      return info;
    }
    return { ...info, parsed_markdown, ai_summary };
  };

  const fetchMaterialDeleteImpact = (
    id: number,
  ): Promise<MaterialDeleteImpact> =>
    get(`${BASE}/material/${id}/delete_impact/`);

  const fetchMaterialUpdateImpact = (
    id: number,
  ): Promise<MaterialUpdateImpact> =>
    get(`${BASE}/material/${id}/update_impact/`);

  const createMaterial = (data: Partial<Material>): Promise<Material> =>
    post(`${BASE}/material/`, data);
  const updateMaterial = (
    id: number,
    data: Partial<Material>,
  ): Promise<Material> => put(`${BASE}/material/${id}/`, data);

  const createMaterialFile = (
    kbId: number,
    name: string,
    file: File,
    ocrEnhance = false,
    metadata: MaterialFileUploadMetadata = {},
  ): Promise<Material> => {
    const fd = new FormData();
    const sourceRelativePath =
      metadata.source_relative_path?.trim() ||
      file.webkitRelativePath?.trim() ||
      file.name;
    fd.append("knowledge_base", String(kbId));
    fd.append("name", name);
    fd.append("material_type", "file");
    fd.append("file", file);
    fd.append("ocr_enhance", String(ocrEnhance));
    fd.append("source_relative_path", sourceRelativePath);
    if (metadata.classification_root_id != null) {
      fd.append(
        "classification_root_id",
        String(metadata.classification_root_id),
      );
    }
    return post(`${BASE}/material/`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  };

  const batchCreateMaterials = (
    kbId: number,
    entries: Array<File | MaterialBatchUploadEntry>,
    ocrEnhance = false,
    classificationRootId?: number | null,
  ): Promise<MaterialBatchCreateResult> => {
    const fd = new FormData();
    fd.append("knowledge_base", String(kbId));
    fd.append("ocr_enhance", String(ocrEnhance));
    if (classificationRootId != null) {
      fd.append("classification_root_id", String(classificationRootId));
    }
    entries.forEach((entry) => {
      const upload = "file" in entry ? entry : { file: entry };
      const sourceRelativePath =
        upload.source_relative_path?.trim() ||
        upload.file.webkitRelativePath?.trim() ||
        upload.file.name;
      fd.append("files", upload.file);
      fd.append("source_relative_paths", sourceRelativePath);
    });
    return post(`${BASE}/material/batch_create/`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  };

  const deleteMaterial = (id: number): Promise<{ pending_review: number }> =>
    del(`${BASE}/material/${id}/`);

  const ingestMaterial = (id: number): Promise<Material> =>
    post(`${BASE}/material/${id}/ingest/`, {});

  const buildMaterial = (
    id: number,
    async = false,
  ): Promise<BuildRecord | { async: boolean }> =>
    post(`${BASE}/material/${id}/build/`, { async });

  const proposeUpdate = (id: number): Promise<BuildRecord> =>
    post(`${BASE}/material/${id}/propose_update/`, {});

  const reindexMaterial = (id: number): Promise<BuildRecord> =>
    post(`${BASE}/material/${id}/reindex/`, {});

  // ---- 页面 ----
  const fetchPages = (
    kbId: number,
    params?: Record<string, unknown>,
  ): Promise<Paged<KnowledgePage>> =>
    get(`${BASE}/page/`, { params: { ...params, knowledge_base: kbId } });

  const fetchDirectoryTree = (kbId: number): Promise<WikiDirectoryTreeResult> =>
    get(`${BASE}/directory/tree/`, { params: { knowledge_base: kbId } });

  const fetchWikiStructure = (kbId: number): Promise<WikiStructureReadResult> =>
    get(`${BASE}/directory/structure/`, { params: { knowledge_base: kbId } });

  const saveWikiStructure = (
    kbId: number,
    payload: WikiStructureSaveRequest,
  ): Promise<WikiStructureSaveResponse> =>
    put(`${BASE}/directory/structure/`, payload, {
      params: { knowledge_base: kbId },
    });

  const previewDirectoryOperation = (
    kbId: number,
    payload: WikiDirectoryOperationRequest,
  ): Promise<WikiDirectoryOperationPreview> =>
    post(`${BASE}/directory/operation_preview/`, payload, {
      params: { knowledge_base: kbId },
    });

  const executeDirectoryOperation = (
    kbId: number,
    payload: WikiDirectoryOperationExecuteRequest,
  ): Promise<WikiDirectoryOperationExecuteResult> =>
    post(`${BASE}/directory/operation_execute/`, payload, {
      params: { knowledge_base: kbId },
    });

  const fetchPage = async (id: number): Promise<KnowledgePage> => {
    const page = (await get(`${BASE}/page/${id}/`)) as KnowledgePage;
    if (!page.knowledge_base) return page;
    const body = await rewriteMarkdownMediaUrls(page?.body || "", async (locators) => {
      const signed = (await post(
        `${BASE}/knowledge_base/${page.knowledge_base}/sign_media/`,
        { locators },
      )) as { urls?: Record<string, string> };
      return signed?.urls || {};
    });
    if (body === (page?.body || "")) return page;
    return { ...page, body };
  };

  const fetchPageSources = (id: number): Promise<WikiPageSourcesResult> =>
    get(`${BASE}/page/${id}/sources/`);

  const createPage = (
    data: Partial<KnowledgePage> & { body?: string },
  ): Promise<KnowledgePage> => post(`${BASE}/page/`, data);

  const saveAnswerPage = (
    data: SaveAnswerPageInput,
  ): Promise<SaveAnswerPageResult> => post(`${BASE}/page/save_answer/`, data);

  const updatePage = (
    id: number,
    data: Partial<KnowledgePage> & { body?: string },
  ): Promise<KnowledgePage> => put(`${BASE}/page/${id}/`, data);

  const deletePage = (
    id: number,
    baseGenerationId?: number,
    structureVersion?: number,
  ): Promise<WikiPageDeleteResult> =>
    del(`${BASE}/page/${id}/`, {
      params:
        baseGenerationId !== undefined && structureVersion !== undefined
          ? {
            base_generation_id: baseGenerationId,
            structure_version: structureVersion,
          }
          : undefined,
    });

  const batchDeletePages = (
    kbId: number,
    ids: number[],
    baseGenerationId?: number,
    structureVersion?: number,
  ): Promise<WikiPageBatchDeleteResult> =>
    post(`${BASE}/page/batch_delete/`, {
      knowledge_base: kbId,
      ids,
      ...(baseGenerationId !== undefined && structureVersion !== undefined
        ? {
          base_generation_id: baseGenerationId,
          structure_version: structureVersion,
        }
        : {}),
    });

  const movePagesToDirectory = (
    kbId: number,
    pageIds: number[],
    targetDirectoryId: number,
    baseGenerationId: number,
    structureVersion: number,
  ): Promise<WikiPageDirectoryMutationResult> =>
    post(`${BASE}/page/move/`, {
      knowledge_base: kbId,
      page_ids: pageIds,
      target_directory_id: targetDirectoryId,
      base_generation_id: baseGenerationId,
      structure_version: structureVersion,
    });

  const restorePagesAutoDirectory = (
    kbId: number,
    pageIds: number[],
    baseGenerationId: number,
    structureVersion: number,
  ): Promise<WikiPageDirectoryMutationResult> =>
    post(`${BASE}/page/restore_auto/`, {
      knowledge_base: kbId,
      page_ids: pageIds,
      base_generation_id: baseGenerationId,
      structure_version: structureVersion,
    });

  const reindexPage = (id: number): Promise<BuildRecord> =>
    post(`${BASE}/page/${id}/reindex/`, {});

  const fetchPageVersions = (id: number): Promise<PageVersion[]> =>
    get(`${BASE}/page/${id}/versions/`);

  const restorePageVersion = (
    id: number,
    version_id: number,
  ): Promise<KnowledgePage> =>
    post(`${BASE}/page/${id}/restore/`, { version_id });

  const restorePageFromArchive = (
    id: number,
    baseGenerationId?: number,
    structureVersion?: number,
  ): Promise<WikiPageRestoreFromArchiveResult> =>
    post(
      `${BASE}/page/${id}/restore_from_archive/`,
      baseGenerationId !== undefined && structureVersion !== undefined
        ? {
          base_generation_id: baseGenerationId,
          structure_version: structureVersion,
        }
        : {},
    );

  const fetchPageDiff = (
    id: number,
    from: number,
    to: number,
  ): Promise<{ diff: string[] }> =>
    get(`${BASE}/page/${id}/diff/`, { params: { from, to } });

  // ---- 构建记录 ----
  const fetchBuildRecords = (
    kbId: number,
    params?: Record<string, unknown>,
  ): Promise<Paged<BuildRecord>> =>
    get(`${BASE}/build_record/`, {
      params: { ...params, knowledge_base: kbId },
    });

  const fetchBuildRecord = (id: number): Promise<BuildRecord> =>
    get(`${BASE}/build_record/${id}/`);

  const retryBuild = (id: number): Promise<{ async: boolean }> =>
    post(`${BASE}/build_record/${id}/retry/`, {});

  const retryBuildMaintenance = (
    id: number,
    stages?: string[],
  ): Promise<BuildRecord> =>
    post(
      `${BASE}/build_record/${id}/retry_maintenance/`,
      stages ? { stages } : {},
    );

  const batchRetryBuildMaintenance = (
    kbId: number,
    ids: number[],
    stages?: string[],
  ): Promise<BuildMaintenanceBatchRetryResult> =>
    post(
      `${BASE}/build_record/batch_retry_maintenance/`,
      stages
        ? { knowledge_base: kbId, ids, stages }
        : { knowledge_base: kbId, ids },
    );

  const cancelBuild = (id: number): Promise<BuildRecord> =>
    post(`${BASE}/build_record/${id}/cancel/`, {});

  // ---- 检查项 ----
  const fetchCheckItems = (
    kbId: number,
    params?: Record<string, unknown>,
  ): Promise<Paged<CheckItem>> =>
    get(`${BASE}/check_item/`, { params: { ...params, knowledge_base: kbId } });

  const fetchDecisionItems = (
    kbId: number,
    params: FetchDecisionItemsParams,
  ): Promise<Paged<CheckItem>> =>
    fetchCheckItems(kbId, {
      ...params,
      decision_only: true,
      view: params.view,
    });

  const decideCheck = (
    id: number,
    payload: CheckDecisionRequest,
  ): Promise<CheckDecisionResponse> =>
    post(`${BASE}/check_item/${id}/decide/`, payload);

  const revokeDecisionRule = (
    id: number,
    payload: RevokeDecisionRuleRequest = {},
  ): Promise<RevokeDecisionRuleResponse> =>
    post(`${BASE}/check_item/${id}/revoke_rule/`, payload);

  const assignCheck = (
    id: number,
    payload: {
      assignee?: string;
      due_at?: string | null;
      action_type?: string;
    },
  ): Promise<CheckItem> => post(`${BASE}/check_item/${id}/assign/`, payload);

  return {
    fetchKnowledgeBases,
    fetchKnowledgeBase,
    enableDirectoryGovernance,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    fetchTemplates,
    fetchLlmModels,
    previewGenerationRollback,
    executeGenerationRollback,
    fetchEmbedProviders,
    generatePurposeSchema,
    search,
    qa,
    qaStream,
    scan,
    fetchRelations,
    rebuildRelations,
    fetchGraph,
    fetchGraphAnalysis,
    fetchOverview,
    buildContext,
    reindexKnowledgeBase,
    exportKnowledgeBaseMarkdown,
    preflightKnowledgeBaseMarkdown,
    executeKnowledgeBaseMarkdown,
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
    fetchDirectoryTree,
    fetchWikiStructure,
    saveWikiStructure,
    previewDirectoryOperation,
    executeDirectoryOperation,
    fetchPage,
    fetchPageSources,
    createPage,
    saveAnswerPage,
    updatePage,
    deletePage,
    batchDeletePages,
    movePagesToDirectory,
    restorePagesAutoDirectory,
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
