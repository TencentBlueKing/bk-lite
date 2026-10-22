import type { RackRoomMode, ViewFocus, ViewType } from './viewTypes';

export interface ParsedViewsSearch {
  model_id: string | undefined;
  /** Aligned with inst_uuids when the URL lists one model per device; length 1 broadcasts. */
  model_ids: string[];
  inst_uuid: string | undefined;
  inst_uuids: string[];
  mode: RackRoomMode | undefined;
  inst_name: string | undefined;
  model_name: string | undefined;
  icn: string | undefined;
}

/** Query keys owned by ViewsWorkspaceShell focus sync — all others are preserved. */
export const FOCUS_QUERY_KEYS = [
  'model_id',
  'inst_uuid',
  'inst_name',
  'model_name',
  'icn',
  'mode',
] as const;

export const parseInstUuids = (raw: string | null | undefined): string[] => {
  if (!raw) return [];
  const seen = new Set<string>();
  const uuids: string[] = [];
  for (const part of raw.split(',')) {
    const uuid = part.trim();
    if (!uuid || seen.has(uuid)) continue;
    seen.add(uuid);
    uuids.push(uuid);
  }
  return uuids;
};

/** Keep order and duplicates. Model ids must stay aligned with inst_uuids. */
export const parseModelIds = (raw: string | null | undefined): string[] => {
  if (!raw) return [];
  return raw.split(',').map((part) => part.trim()).filter(Boolean);
};

/**
 * Pair devices with models.
 * One model id applies to every uuid (rack compare, single-model views).
 * Several model ids must be the same length as the uuid list; otherwise the link is invalid.
 */
export const alignViewFocusModels = (
  modelIds: string[],
  instUuids: string[]
): { model_id: string; inst_uuid: string }[] => {
  if (!modelIds.length || !instUuids.length) return [];
  if (modelIds.length === 1) {
    return instUuids.map((inst_uuid) => ({
      model_id: modelIds[0],
      inst_uuid,
    }));
  }
  if (modelIds.length !== instUuids.length) return [];
  return instUuids.map((inst_uuid, index) => ({
    model_id: modelIds[index],
    inst_uuid,
  }));
};

const asFocusList = (focus: ViewFocus | ViewFocus[]): ViewFocus[] =>
  Array.isArray(focus) ? focus.filter((item) => item?.inst_uuid) : (focus?.inst_uuid ? [focus] : []);

/** Detail links still carry instance identity. View pages keep the selection in browser storage. */
const appendInstanceParams = (
  params: URLSearchParams,
  focus: ViewFocus | ViewFocus[],
): void => {
  const focuses = asFocusList(focus);
  const primary = focuses[0];
  if (!primary) return;
  const modelIds = focuses.map((item) => item.model_id);
  const sameModel = modelIds.every((modelId) => modelId === modelIds[0]);
  params.set('model_id', sameModel ? modelIds[0] : modelIds.join(','));
  params.set('inst_uuid', focuses.map((item) => item.inst_uuid).join(','));
  if (primary.inst_name) params.set('inst_name', primary.inst_name);
  if (primary.model_name) params.set('model_name', primary.model_name);
  if (primary.icn) params.set('icn', primary.icn);
  if (primary.mode) params.set('mode', primary.mode);
};

/** Views URLs keep only the short rack/room mode. The instance list stays in localStorage. */
const appendViewsFocusParams = (
  params: URLSearchParams,
  focus: ViewFocus | ViewFocus[],
): void => {
  const primary = asFocusList(focus)[0];
  if (primary?.mode) params.set('mode', primary.mode);
};

const clearFocusParams = (params: URLSearchParams): void => {
  for (const key of FOCUS_QUERY_KEYS) {
    params.delete(key);
  }
};

export const buildViewsPath = (
  viewType: ViewType,
  focus: ViewFocus | ViewFocus[],
): string => {
  const params = new URLSearchParams();
  appendViewsFocusParams(params, focus);
  const query = params.toString();
  return query
    ? `/cmdb/views/${viewType}?${query}`
    : `/cmdb/views/${viewType}`;
};

/**
 * Refresh the views URL: drop instance identity, keep rack/room mode and
 * unrelated UI query keys (e.g. K8S hub `sub`, `expanded_workloads`).
 */
export const buildViewsPathPreserving = (
  viewType: ViewType,
  focus: ViewFocus | ViewFocus[],
  currentSearchParams: URLSearchParams
): string => {
  const params = new URLSearchParams(currentSearchParams.toString());
  clearFocusParams(params);
  appendViewsFocusParams(params, focus);
  const query = params.toString();
  return query
    ? `/cmdb/views/${viewType}?${query}`
    : `/cmdb/views/${viewType}`;
};

export const buildBaseInfoPath = (focus: ViewFocus): string => {
  const params = new URLSearchParams();
  appendInstanceParams(params, focus);
  return `/cmdb/assetData/detail/baseInfo?${params.toString()}`;
};

const parseMode = (value: string | null): RackRoomMode | undefined => {
  if (value === 'room' || value === 'rack') return value;
  return undefined;
};

export const parseViewsSearch = (searchParams: URLSearchParams): ParsedViewsSearch => {
  const inst_uuids = parseInstUuids(searchParams.get('inst_uuid'));
  const model_ids = parseModelIds(searchParams.get('model_id'));
  return {
    model_id: model_ids[0],
    model_ids,
    inst_uuid: inst_uuids[0],
    inst_uuids,
    mode: parseMode(searchParams.get('mode')),
    inst_name: searchParams.get('inst_name') ?? undefined,
    model_name: searchParams.get('model_name') ?? undefined,
    icn: searchParams.get('icn') ?? undefined,
  };
};
