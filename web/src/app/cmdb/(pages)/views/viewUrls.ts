import type { RackRoomMode, ViewFocus, ViewType } from './viewTypes';

export interface ParsedViewsSearch {
  model_id: string | undefined;
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

const asFocusList = (focus: ViewFocus | ViewFocus[]): ViewFocus[] =>
  Array.isArray(focus) ? focus.filter((item) => item?.inst_uuid) : (focus?.inst_uuid ? [focus] : []);

const appendFocusParams = (
  params: URLSearchParams,
  focus: ViewFocus | ViewFocus[],
): void => {
  const focuses = asFocusList(focus);
  const primary = focuses[0];
  if (!primary) return;
  params.set('model_id', primary.model_id);
  params.set('inst_uuid', focuses.map((item) => item.inst_uuid).join(','));
  if (primary.inst_name) params.set('inst_name', primary.inst_name);
  if (primary.model_name) params.set('model_name', primary.model_name);
  if (primary.icn) params.set('icn', primary.icn);
  if (primary.mode) params.set('mode', primary.mode);
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
  appendFocusParams(params, focus);
  return `/cmdb/views/${viewType}?${params.toString()}`;
};

/**
 * Sync focus into the views URL while preserving non-focus UI query keys
 * (e.g. K8S hub `sub`, `expanded_workloads`).
 */
export const buildViewsPathPreserving = (
  viewType: ViewType,
  focus: ViewFocus | ViewFocus[],
  currentSearchParams: URLSearchParams
): string => {
  const params = new URLSearchParams(currentSearchParams.toString());
  clearFocusParams(params);
  appendFocusParams(params, focus);
  const query = params.toString();
  return query
    ? `/cmdb/views/${viewType}?${query}`
    : `/cmdb/views/${viewType}`;
};

export const buildBaseInfoPath = (focus: ViewFocus): string => {
  const params = new URLSearchParams();
  appendFocusParams(params, focus);
  return `/cmdb/assetData/detail/baseInfo?${params.toString()}`;
};

const parseMode = (value: string | null): RackRoomMode | undefined => {
  if (value === 'room' || value === 'rack') return value;
  return undefined;
};

export const parseViewsSearch = (searchParams: URLSearchParams): ParsedViewsSearch => {
  const inst_uuids = parseInstUuids(searchParams.get('inst_uuid'));
  return {
    model_id: searchParams.get('model_id') ?? undefined,
    inst_uuid: inst_uuids[0],
    inst_uuids,
    mode: parseMode(searchParams.get('mode')),
    inst_name: searchParams.get('inst_name') ?? undefined,
    model_name: searchParams.get('model_name') ?? undefined,
    icn: searchParams.get('icn') ?? undefined,
  };
};
