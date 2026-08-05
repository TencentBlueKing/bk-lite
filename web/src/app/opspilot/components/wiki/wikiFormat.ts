// 时间统一格式化:直接从后端(Django 当前时区)返回的 ISO 串中提取"年月日 时分秒",
// 展示为 YYYY-MM-DD HH:mm:ss —— 去掉 "T"、毫秒与 "+0800" 偏移后缀,不做浏览器本地时区换算。
export const formatWikiTime = (v?: string | null): string => {
  if (!v) return "--";
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(v);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}` : v;
};

/** Format seconds as compact duration, e.g. 65 → 1m 5s, 3661 → 1h 1m 1s. */
export const formatWikiDuration = (seconds?: number | null): string => {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "--";
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
};

// 构建记录:触发/阶段/状态 → i18n key(避免界面直接显示 material / done / success 这类裸 key)
export const TRIGGER_LABEL: Record<string, string> = {
  material: "wiki.triggerMaterial",
  material_delete: "wiki.triggerMaterialDelete",
  material_update: "wiki.triggerMaterialUpdate",
  rebuild: "wiki.triggerRebuild",
};
export const STAGE_LABEL: Record<string, string> = {
  done: "wiki.stageDone",
  failed: "wiki.stageFailed",
  generating: "wiki.stageGenerating",
  running: "wiki.stageRunning",
  cancelled: "wiki.stageCancelled",
};
export const BUILD_STATUS_LABEL: Record<string, string> = {
  success: "wiki.buildSuccess",
  running: "wiki.buildRunning",
  partial: "wiki.buildPartial",
  failed: "wiki.buildFailed",
  cancelled: "wiki.buildCancelled",
};

export type MaterialDisplayStatus = "pending" | "building" | "built" | "failed";

export const materialDisplayStatus = (
  status?: string,
): MaterialDisplayStatus => {
  if (status === "parsing" || status === "building") return "building";
  if (status === "built") return "built";
  if (
    status === "parse_failed" ||
    status === "build_failed" ||
    status === "failed" ||
    status === "invalid" ||
    status === "partial"
  ) {
    return "failed";
  }
  return "pending";
};

export const MATERIAL_STATUS_META: Record<
  MaterialDisplayStatus,
  { color: string; key: string }
> = {
  pending: { color: "default", key: "wiki.statusPending" },
  building: { color: "processing", key: "wiki.statusBuilding" },
  built: { color: "green", key: "wiki.statusBuilt" },
  failed: { color: "red", key: "wiki.statusFailed" },
};

// 知识页面状态 → i18n key(active / archived / source_invalid)
export const PAGE_STATUS_LABEL: Record<string, string> = {
  active: "wiki.statusActive",
  archived: "wiki.statusArchived",
  source_invalid: "wiki.statusSourceInvalid",
};

// 索引对象状态 → i18n key
export const INDEX_STATUS_LABEL: Record<string, string> = {
  indexed: "wiki.indexStatusIndexed",
  indexing: "wiki.indexStatusIndexing",
  not_indexed: "wiki.indexStatusNotIndexed",
  failed: "wiki.indexStatusFailed",
  skipped: "wiki.indexStatusSkipped",
};

export const INDEX_REASON_LABEL: Record<string, string> = {
  no_embed_provider: "wiki.indexReasonNoEmbedProvider",
  no_current_version: "wiki.indexReasonNoCurrentVersion",
  empty_body: "wiki.indexReasonEmptyBody",
};

// 知识页面类型 → i18n key（图谱过滤器等处避免直接展示 entity/source 裸 key）
export const PAGE_TYPE_LABEL: Record<string, string> = {
  concept: "wiki.pageTypeConcept",
  entity: "wiki.pageTypeEntity",
  source: "wiki.pageTypeSource",
  query: "wiki.pageTypeQuery",
  comparison: "wiki.pageTypeComparison",
  synthesis: "wiki.pageTypeSynthesis",
  procedure: "wiki.pageTypeProcedure",
  faq: "wiki.pageTypeFaq",
  other: "wiki.pageTypeOther",
};

export const pageTypeLabelKey = (pageType?: string | null): string => {
  const normalized = String(pageType || "")
    .trim()
    .toLowerCase();
  return PAGE_TYPE_LABEL[normalized] || "";
};
