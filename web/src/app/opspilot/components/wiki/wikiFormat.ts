// 时间统一格式化:直接从后端(Django 当前时区)返回的 ISO 串中提取"年月日 时分秒",
// 展示为 YYYY-MM-DD HH:mm:ss —— 去掉 "T"、毫秒与 "+0800" 偏移后缀,不做浏览器本地时区换算。
export const formatWikiTime = (v?: string | null): string => {
  if (!v) return '--';
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(v);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}` : v;
};

// 构建记录:触发/阶段/状态 → i18n key(避免界面直接显示 material / done / success 这类裸 key)
export const TRIGGER_LABEL: Record<string, string> = {
  material: 'wiki.triggerMaterial',
  material_delete: 'wiki.triggerMaterialDelete',
  material_update: 'wiki.triggerMaterialUpdate',
  rebuild: 'wiki.triggerRebuild',
};
export const STAGE_LABEL: Record<string, string> = {
  done: 'wiki.stageDone',
  failed: 'wiki.stageFailed',
  generating: 'wiki.stageGenerating',
  running: 'wiki.stageRunning',
  cancelled: 'wiki.stageCancelled',
};
export const BUILD_STATUS_LABEL: Record<string, string> = {
  success: 'wiki.buildSuccess',
  running: 'wiki.buildRunning',
  partial: 'wiki.buildPartial',
  failed: 'wiki.buildFailed',
  cancelled: 'wiki.buildCancelled',
};

// 知识页面状态 → i18n key(active / archived / source_invalid)
export const PAGE_STATUS_LABEL: Record<string, string> = {
  active: 'wiki.statusActive',
  archived: 'wiki.statusArchived',
  source_invalid: 'wiki.statusSourceInvalid',
};

// 索引对象状态 → i18n key
export const INDEX_STATUS_LABEL: Record<string, string> = {
  indexed: 'wiki.indexStatusIndexed',
  indexing: 'wiki.indexStatusIndexing',
  not_indexed: 'wiki.indexStatusNotIndexed',
  failed: 'wiki.indexStatusFailed',
  skipped: 'wiki.indexStatusSkipped',
};

export const INDEX_REASON_LABEL: Record<string, string> = {
  no_embed_provider: 'wiki.indexReasonNoEmbedProvider',
  no_current_version: 'wiki.indexReasonNoCurrentVersion',
  empty_body: 'wiki.indexReasonEmptyBody',
};
