export const ASSET_PAGE_SIZE = 20;
export const FOLLOWED_ASSETS_CONFIG_KEY = 'cmdb_followed_assets';
export const MAX_FOLLOWED_ASSETS = 100;

export interface AssetClassification { id: string; name: string; order: number; visible: boolean; }
export interface AssetModel { id: string; name: string; classificationId: string; icon: string; order: number; visible: boolean; count: number; }
export interface AssetInstance {
  id: string | number;
  modelId: string;
  name: string;
  organizationName: string;
  values: Record<string, unknown>;
}
export interface AssetField { id: string; name: string; type: string; option: unknown; order: number; }
export interface AssetFieldGroup { id: string | number; name: string; order: number; collapsed: boolean; fields: AssetField[]; }
export interface FollowedAssetItem { modelId: string; instanceId: string | number; followedAt: string; }
export interface FollowedAssetsConfig { items: FollowedAssetItem[]; }
export interface SearchModelStat { modelId: string; count: number; }
export interface PageResult<T> { count: number; items: T[]; }

export function assetRequestErrorKind(error: unknown): 'forbidden' | 'missing' | 'error' {
  if (!(error instanceof Error)) return 'error';
  if (/API Error:\s*403\b/.test(error.message)) return 'forbidden';
  if (/API Error:\s*404\b/.test(error.message)) return 'missing';
  return 'error';
}

const sameAsset = (item: FollowedAssetItem, modelId: string, instanceId: string | number) => item.modelId === modelId && String(item.instanceId) === String(instanceId);
export function normalizeFollowedConfig(value: unknown): FollowedAssetsConfig {
  const source = typeof value === 'object' && value !== null ? value as { items?: unknown } : {};
  const items = (Array.isArray(source.items) ? source.items : []).flatMap((raw) => {
    if (typeof raw !== 'object' || raw === null) return [];
    const item = raw as Record<string, unknown>; const modelId = String(item.model_id || ''); const instanceId = item.inst_id as string | number;
    if (!modelId || instanceId === undefined || instanceId === null) return [];
    return [{ modelId, instanceId, followedAt: String(item.followed_at || '') }];
  }).sort((a, b) => new Date(b.followedAt || 0).getTime() - new Date(a.followedAt || 0).getTime()).slice(0, MAX_FOLLOWED_ASSETS);
  return { items };
}
export function isAssetFollowed(config: FollowedAssetsConfig, modelId: string, instanceId: string | number) { return config.items.some((item) => sameAsset(item, modelId, instanceId)); }
export function addFollowedAsset(config: FollowedAssetsConfig, modelId: string, instanceId: string | number, followedAt = new Date().toISOString()): FollowedAssetsConfig {
  return { items: [{ modelId, instanceId, followedAt }, ...config.items.filter((item) => !sameAsset(item, modelId, instanceId))].slice(0, MAX_FOLLOWED_ASSETS) };
}
export function removeFollowedAsset(config: FollowedAssetsConfig, modelId: string, instanceId: string | number): FollowedAssetsConfig { return { items: config.items.filter((item) => !sameAsset(item, modelId, instanceId)) }; }
export function serializeFollowedConfig(config: FollowedAssetsConfig) { return { items: config.items.map((item) => ({ model_id: item.modelId, inst_id: item.instanceId, followed_at: item.followedAt })) }; }

export function groupAssetModels(classifications: readonly AssetClassification[], models: readonly AssetModel[]) {
  return classifications.filter((item) => item.visible).sort((a, b) => a.order - b.order).map((classification) => ({
    classification, models: models.filter((model) => model.visible && model.classificationId === classification.id).sort((a, b) => a.order - b.order),
  })).filter((group) => group.models.length);
}

/** 按分类顺序展开的可见模型列表，供默认选中与邻近轨使用 */
export function orderedAssetModels(
  classifications: readonly AssetClassification[],
  models: readonly AssetModel[],
) {
  return groupAssetModels(classifications, models).flatMap((group) => group.models);
}

/** 某分类下的可见模型（按 order） */
export function modelsInClassification(
  models: readonly AssetModel[],
  classificationId: string,
) {
  return models
    .filter((model) => model.visible && model.classificationId === classificationId)
    .sort((a, b) => a.order - b.order);
}

/** 记忆模型失效时：优先 count>0，否则取有序第一个 */
export function resolveDefaultAssetModel(
  models: readonly AssetModel[],
  preferredId = '',
) {
  if (preferredId) {
    const preferred = models.find((model) => model.id === preferredId);
    if (preferred) return preferred;
  }
  return models.find((model) => model.count > 0) || models[0] || null;
}

/** 由模型反查分类；模型不可见或不存在时返回空串 */
export function classificationIdForModel(
  models: readonly AssetModel[],
  modelId: string,
) {
  return models.find((model) => model.visible && model.id === modelId)?.classificationId || '';
}

/** 同分类邻居（含自身），用于横向邻近 chip，不全量铺轨 */
export function neighborAssetModels(
  models: readonly AssetModel[],
  modelId: string,
) {
  const current = models.find((model) => model.id === modelId);
  if (!current) return [] as AssetModel[];
  return modelsInClassification(models, current.classificationId);
}

/** 后端 DisplayFieldHandler 会为这些类型挂 `${attr_id}_display`（可读名，非原始 ID） */
const ASSET_DISPLAY_FIELD_TYPES = new Set([
  'organization',
  'user',
  'enum',
  'tag',
  'table',
  'attachment',
  'image',
]);

function displayText(value: unknown): string {
  if (value === undefined || value === null) return '';
  const text = String(value).trim();
  return text;
}

function enumOptionName(options: unknown[], candidate: unknown): string {
  const key = String(candidate);
  const match = options.find((option) => {
    if (typeof option !== 'object' || option === null) return false;
    return String((option as Record<string, unknown>).id) === key;
  }) as Record<string, unknown> | undefined;
  return match ? String(match.name || '') : '';
}

function tagItemText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value).trim();
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const candidate = record.value ?? record.label ?? record.name ?? record.key;
    if (candidate !== undefined && candidate !== null) return String(candidate).trim();
  }
  return String(value).trim();
}

function fileNamesText(value: unknown): string {
  const items = Array.isArray(value) ? value : [];
  const names = items.flatMap((item) => {
    if (typeof item !== 'object' || item === null) return [];
    const name = (item as Record<string, unknown>).name;
    return name === undefined || name === null || name === '' ? [] : [String(name)];
  });
  return names.join(', ');
}

function tableCellsText(value: unknown): string {
  let rows: unknown[] = [];
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      rows = Array.isArray(parsed) ? parsed : [];
    } catch {
      return value.trim();
    }
  } else if (Array.isArray(value)) {
    rows = value;
  }
  const cells = rows.flatMap((row) => {
    if (typeof row !== 'object' || row === null) return [];
    return Object.values(row as Record<string, unknown>)
      .filter((cell) => cell !== undefined && cell !== null && cell !== '')
      .map((cell) => String(cell));
  });
  return cells.join(', ');
}

/**
 * 资产字段可读文案。对齐 Web 只读详情：组织/用户等优先用后端 `*_display`，
 * 避免把原始 ID 直接 String() 出来（如组织显示成「1」）。
 */
export function assetValueText(
  field: AssetField,
  value: unknown,
  yes: string,
  no: string,
  formatTime: (value: string) => string,
  displayValue?: unknown,
): string {
  if (ASSET_DISPLAY_FIELD_TYPES.has(field.type)) {
    const fromDisplay = displayText(displayValue);
    if (fromDisplay) return fromDisplay;
  }

  if (field.type === 'pwd') {
    if (value === undefined || value === null || value === '') return '--';
    return '***';
  }

  if (value === undefined || value === null || value === '') return '--';

  if (field.type === 'bool') return value ? yes : no;

  if (field.type === 'enum') {
    const options = Array.isArray(field.option) ? field.option : [];
    if (Array.isArray(value)) {
      return value.map((item) => enumOptionName(options, item)).filter(Boolean).join(', ') || '--';
    }
    return enumOptionName(options, value) || '--';
  }

  if (field.type === 'time') return formatTime(String(value));

  if (field.type === 'tag') {
    if (Array.isArray(value)) {
      return value.map(tagItemText).filter(Boolean).join(', ') || '--';
    }
    return tagItemText(value) || '--';
  }

  if (field.type === 'table') {
    return tableCellsText(value) || '--';
  }

  if (field.type === 'attachment' || field.type === 'image') {
    return fileNamesText(value) || '--';
  }

  // 组织/用户在无 _display 时不应回落成原始 ID
  if (field.type === 'organization' || field.type === 'user') return '--';

  if (Array.isArray(value)) return value.map(String).join(', ') || '--';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return '--';
    }
  }
  return String(value);
}
