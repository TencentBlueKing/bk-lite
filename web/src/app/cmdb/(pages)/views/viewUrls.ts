import type { RackRoomMode, ViewFocus, ViewType } from './viewTypes';

export interface ParsedViewsSearch {
  model_id: string | undefined;
  inst_uuid: string | undefined;
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

const appendFocusParams = (params: URLSearchParams, focus: ViewFocus): void => {
  params.set('model_id', focus.model_id);
  params.set('inst_uuid', focus.inst_uuid);
  if (focus.inst_name) params.set('inst_name', focus.inst_name);
  if (focus.model_name) params.set('model_name', focus.model_name);
  if (focus.icn) params.set('icn', focus.icn);
  if (focus.mode) params.set('mode', focus.mode);
};

const clearFocusParams = (params: URLSearchParams): void => {
  for (const key of FOCUS_QUERY_KEYS) {
    params.delete(key);
  }
};

export const buildViewsPath = (viewType: ViewType, focus: ViewFocus): string => {
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
  focus: ViewFocus,
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

export const parseViewsSearch = (searchParams: URLSearchParams): ParsedViewsSearch => ({
  model_id: searchParams.get('model_id') ?? undefined,
  inst_uuid: searchParams.get('inst_uuid') ?? undefined,
  mode: parseMode(searchParams.get('mode')),
  inst_name: searchParams.get('inst_name') ?? undefined,
  model_name: searchParams.get('model_name') ?? undefined,
  icn: searchParams.get('icn') ?? undefined,
});
