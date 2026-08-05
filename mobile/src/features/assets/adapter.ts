import { apiGet, apiPost } from '@/api/request';
import { FOLLOWED_ASSETS_CONFIG_KEY, normalizeFollowedConfig, serializeFollowedConfig, type AssetClassification, type AssetFieldGroup, type AssetInstance, type AssetModel, type FollowedAssetsConfig, type PageResult, type SearchModelStat } from './model';

function record(value: unknown): Record<string, unknown> { return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}; }
function text(value: unknown) { return value === null || value === undefined ? '' : String(value); }
function number(value: unknown) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0; }
function unwrap<T>(value: unknown): T { const data = record(value); if (typeof data.result !== 'boolean') return value as T; if (!data.result) throw new Error(text(data.message) || 'Server returned an error'); return data.data as T; }
function unwrapDeep(value: unknown) { let current = value; for (let index = 0; index < 2; index += 1) { const next = record(current); if (typeof next.result !== 'boolean') break; if (!next.result) throw new Error(text(next.message) || 'Server returned an error'); current = next.data; } return current; }
function mapInstance(value: unknown, fallbackModelId: string): AssetInstance {
  const item = record(value);
  const id = item._id as string | number;
  return {
    id,
    modelId: text(item.model_id || fallbackModelId),
    name: text(item.inst_name || item.ip_addr || id),
    organizationName: text(item.organization_display),
    values: item,
  };
}

export async function listAssetCatalog(signal?: AbortSignal) {
  const [classRaw, modelRaw, countRaw] = await Promise.all([
    apiGet('/cmdb/api/classification/', undefined, { signal }), apiGet('/cmdb/api/model/', undefined, { signal }), apiGet('/cmdb/api/instance/model_inst_count/', undefined, { signal }),
  ]);
  const counts = record(unwrap<unknown>(countRaw));
  const classifications: AssetClassification[] = (Array.isArray(unwrap<unknown>(classRaw)) ? unwrap<unknown[]>(classRaw) : []).map((value) => { const item = record(value); return { id: text(item.classification_id), name: text(item.classification_name || item.classification_id), order: number(item.order), visible: item.is_visible !== false }; }).filter((item) => item.id && item.visible);
  const models: AssetModel[] = (Array.isArray(unwrap<unknown>(modelRaw)) ? unwrap<unknown[]>(modelRaw) : []).map((value) => { const item = record(value); const id = text(item.model_id); return { id, name: text(item.model_name || id), classificationId: text(item.classification_id), icon: text(item.icn), order: number(item.order_id), visible: item.is_visible !== false, count: number(counts[id]) }; }).filter((item) => item.id && item.visible);
  return { classifications, models };
}

export async function listAssetInstances(modelId: string, page = 1, keyword = '', signal?: AbortSignal): Promise<PageResult<AssetInstance>> {
  const raw = record(unwrap<unknown>(await apiPost('/cmdb/api/instance/search/', { query_list: keyword ? [{ field: 'inst_name', type: 'str', value: keyword }] : [], page, page_size: 20, order: '', model_id: modelId, role: '', case_sensitive: false }, { signal })));
  return { count: number(raw.count), items: (Array.isArray(raw.insts) ? raw.insts : []).map((item) => mapInstance(item, modelId)).filter((item) => item.id !== undefined && item.id !== null) };
}

export async function resolveFollowedAssets(config: FollowedAssetsConfig, models: readonly AssetModel[], signal?: AbortSignal) {
  const grouped = new Map<string, Array<string | number>>(); config.items.forEach((item) => grouped.set(item.modelId, [...(grouped.get(item.modelId) || []), item.instanceId]));
  const settled = await Promise.allSettled(Array.from(grouped.entries()).map(async ([modelId, ids]) => {
    const raw = record(unwrap<unknown>(await apiPost('/cmdb/api/instance/search/', { model_id: modelId, query_list: [{ field: 'id', type: 'id[]', value: ids }], page: 1, page_size: ids.length }, { signal })));
    return (Array.isArray(raw.insts) ? raw.insts : []).map((item) => mapInstance(item, modelId));
  }));
  const byKey = new Map<string, AssetInstance>(); settled.forEach((result) => { if (result.status === 'fulfilled') result.value.forEach((item) => byKey.set(`${item.modelId}:${String(item.id)}`, item)); });
  const modelIds = new Set(models.map((model) => model.id));
  return config.items.flatMap((item) => { if (!modelIds.has(item.modelId)) return []; const detail = byKey.get(`${item.modelId}:${String(item.instanceId)}`); return detail ? [detail] : []; });
}

export async function getAssetInstance(instanceId: string | number, signal?: AbortSignal) { return mapInstance(unwrap<unknown>(await apiGet(`/cmdb/api/instance/${instanceId}/`, undefined, { signal })), ''); }
export async function getAssetFieldGroups(modelId: string, signal?: AbortSignal): Promise<{ modelId: string; modelName: string; groups: AssetFieldGroup[] }> {
  const raw = record(unwrap<unknown>(await apiGet('/cmdb/api/field_groups/full_info/', { model_id: modelId }, { signal })));
  const groups = (Array.isArray(raw.groups) ? raw.groups : []).map((value) => { const item = record(value); return {
    id: item.id as string | number, name: text(item.group_name), order: number(item.order), collapsed: Boolean(item.is_collapsed),
    fields: (Array.isArray(item.attrs) ? item.attrs : []).map((rawField) => { const field = record(rawField); return { id: text(field.attr_id), name: text(field.attr_name || field.attr_id), type: text(field.attr_type), option: field.option, order: number(field.order) }; }).filter((field) => field.id).sort((a, b) => a.order - b.order),
  }; }).sort((a, b) => a.order - b.order);
  return { modelId: text(raw.model_id || modelId), modelName: text(raw.model_name || raw.model_id || modelId), groups };
}

export async function getFollowedConfig(signal?: AbortSignal) { const raw = unwrapDeep(await apiGet(`/cmdb/api/user_configs/by_key/${FOLLOWED_ASSETS_CONFIG_KEY}/`, undefined, { signal })); const data = record(raw); return normalizeFollowedConfig(data.data ?? raw); }
export async function updateFollowedConfig(config: FollowedAssetsConfig, signal?: AbortSignal) { await apiPost('/cmdb/api/user_configs/update_key/', { config_key: FOLLOWED_ASSETS_CONFIG_KEY, config_value: serializeFollowedConfig(config) }, { signal }); }

export async function searchAssetStats(search: string, exact: boolean, signal?: AbortSignal) { const raw = record(unwrap<unknown>(await apiPost('/cmdb/api/instance/fulltext_search/stats/', { search, case_sensitive: exact }, { signal }))); return { count: number(raw.total), models: (Array.isArray(raw.model_stats) ? raw.model_stats : []).map((value) => { const item = record(value); return { modelId: text(item.model_id), count: number(item.count) } as SearchModelStat; }).filter((item) => item.modelId && item.count > 0) }; }
export async function searchAssetsByModel(search: string, modelId: string, exact: boolean, page = 1, signal?: AbortSignal): Promise<PageResult<AssetInstance>> { const raw = record(unwrap<unknown>(await apiPost('/cmdb/api/instance/fulltext_search/by_model/', { search, model_id: modelId, page, page_size: 20, case_sensitive: exact }, { signal }))); return { count: number(raw.total), items: (Array.isArray(raw.data) ? raw.data : []).map((item) => mapInstance(item, modelId)) }; }
