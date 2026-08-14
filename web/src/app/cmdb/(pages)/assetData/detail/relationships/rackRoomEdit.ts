export const RACK_ROOM_ASSET_PERMISSION_PATH = '/cmdb/assetData';

export const PLACEABLE_DEVICE_MODELS = [
  'switch',
  'router',
  'firewall',
  'loadbalance',
  'physcial_server',
] as const;

export type PlaceableDeviceModel = (typeof PLACEABLE_DEVICE_MODELS)[number];

export const LAYOUT_ACTION_PLACE_CREATE = 'place_create';
export const LAYOUT_ACTION_PLACE_EXISTING = 'place_existing';
export const LAYOUT_ACTION_UNPLACE = 'unplace';

export type LayoutAction =
  | typeof LAYOUT_ACTION_PLACE_CREATE
  | typeof LAYOUT_ACTION_PLACE_EXISTING
  | typeof LAYOUT_ACTION_UNPLACE;

export const CANDIDATE_SELECTABLE = 'selectable';
export const CANDIDATE_OCCUPIED = 'occupied_elsewhere';
export const CANDIDATE_ALREADY_PLACED = 'already_placed';

export type LayoutCandidateStatus =
  | typeof CANDIDATE_SELECTABLE
  | typeof CANDIDATE_OCCUPIED
  | typeof CANDIDATE_ALREADY_PLACED;

export const RACK_LOCKED_ATTR_IDS = ['location'] as const;
export const DEVICE_LOCKED_ATTR_IDS = ['rack_u_start'] as const;

export const DEVICE_DRAWER_HEADER_ATTR_IDS = ['inst_name', 'rack_u_start', 'u_size'] as const;

export interface DeviceDrawerAttr {
  attr_id: string;
  attr_name?: string;
  attr_type?: string;
  option?: unknown;
  is_system_link?: boolean;
  is_display_field?: boolean;
}

export interface DeviceDrawerRow {
  key: string;
  label: string;
  value: string;
}

export function isPlaceableDeviceModel(modelId: string): modelId is PlaceableDeviceModel {
  return (PLACEABLE_DEVICE_MODELS as readonly string[]).includes(modelId);
}

export function formatRackLocationLabel(row: number, col: number): string {
  return `${String.fromCharCode(64 + col)}${String(row).padStart(2, '0')}`;
}

export function normalizeDeviceUSize(value: unknown, fallback = 1): number {
  const parsed = Number(value);
  if (Number.isInteger(parsed) && parsed > 0) return parsed;
  return fallback;
}

export function occupiedUSet(
  placed: Array<{ rack_u_start?: number; u_size?: number; u_end?: number }>
): Set<number> {
  const occupied = new Set<number>();
  for (const device of placed || []) {
    const start = Number(device.rack_u_start);
    const end = Number(device.u_end || (start && device.u_size ? start + Number(device.u_size) - 1 : 0));
    if (!start || !end) continue;
    for (let u = start; u <= end; u += 1) occupied.add(u);
  }
  return occupied;
}

export function hasInstanceOperate(permission: unknown): boolean {
  return Array.isArray(permission) && permission.includes('Operate');
}

export function canPlaceOnEmpty(input: { hasAdd: boolean; hasEdit: boolean }): boolean {
  return input.hasAdd || input.hasEdit;
}

export function canUnplaceFromLayout(input: {
  hasEdit: boolean;
  instOperate: boolean;
}): boolean {
  return input.hasEdit && input.instOperate;
}

export function candidateIsSelectable(status: string | undefined): boolean {
  return status === CANDIDATE_SELECTABLE;
}

export function candidateOpensDetail(status: string | undefined): boolean {
  return status === CANDIDATE_OCCUPIED;
}

export function buildInstanceDetailPath(input: {
  modelId: string;
  instUuid: string;
  instName?: string;
}): string {
  const params = new URLSearchParams({
    icn: '',
    model_name: input.modelId,
    model_id: input.modelId,
    classification_id: '',
    inst_uuid: input.instUuid,
    inst_name: input.instName || '',
  });
  return `/cmdb/assetData/detail/baseInfo?${params.toString()}`;
}

export function openInstanceDetail(input: {
  modelId: string;
  instUuid: string;
  instName?: string;
}): void {
  window.open(buildInstanceDetailPath(input), '_blank', 'noopener,noreferrer');
}

export interface LayoutChangePayload {
  action: LayoutAction;
  scope: 'room' | 'rack';
  container_inst_uuid: string;
  inst_uuid?: string;
  model_id?: string;
  instance_info?: Record<string, unknown>;
  row?: number;
  col?: number;
  u_start?: number;
  u_size?: number;
}

export function buildPlaceCreatePayload(input: {
  scope: 'room' | 'rack';
  containerInstUuid: string;
  modelId: string;
  instanceInfo: Record<string, unknown>;
  row?: number;
  col?: number;
  uStart?: number;
  uSize?: number;
}): LayoutChangePayload {
  return {
    action: LAYOUT_ACTION_PLACE_CREATE,
    scope: input.scope,
    container_inst_uuid: input.containerInstUuid,
    model_id: input.modelId,
    instance_info: input.instanceInfo,
    row: input.row,
    col: input.col,
    u_start: input.uStart,
    u_size: input.uSize,
  };
}

export function buildPlaceExistingPayload(input: {
  scope: 'room' | 'rack';
  containerInstUuid: string;
  instUuid: string;
  row?: number;
  col?: number;
  uStart?: number;
  uSize?: number;
}): LayoutChangePayload {
  return {
    action: LAYOUT_ACTION_PLACE_EXISTING,
    scope: input.scope,
    container_inst_uuid: input.containerInstUuid,
    inst_uuid: input.instUuid,
    row: input.row,
    col: input.col,
    u_start: input.uStart,
    u_size: input.uSize,
  };
}

export function buildUnplacePayload(input: {
  scope: 'room' | 'rack';
  containerInstUuid: string;
  instUuid: string;
}): LayoutChangePayload {
  return {
    action: LAYOUT_ACTION_UNPLACE,
    scope: input.scope,
    container_inst_uuid: input.containerInstUuid,
    inst_uuid: input.instUuid,
  };
}

export function unplaceClearsDeviceStartOnly(attrs: Record<string, unknown>): boolean {
  return 'rack_u_start' in attrs && !('u_size' in attrs);
}

export function normalizeModelAttrList(raw: unknown): DeviceDrawerAttr[] {
  if (Array.isArray(raw)) return raw as DeviceDrawerAttr[];
  if (raw && typeof raw === 'object' && Array.isArray((raw as { attrs?: unknown }).attrs)) {
    return (raw as { attrs: DeviceDrawerAttr[] }).attrs;
  }
  return [];
}

export function listDeviceDrawerAttrs(
  attrs: DeviceDrawerAttr[] | null | undefined
): DeviceDrawerAttr[] {
  const skip = new Set<string>(DEVICE_DRAWER_HEADER_ATTR_IDS);
  return (attrs || []).filter((attr) => {
    if (!attr?.attr_id) return false;
    if (skip.has(attr.attr_id)) return false;
    if (attr.is_system_link || attr.is_display_field) return false;
    if (attr.attr_type === 'table') return false;
    return true;
  });
}

function enumOptionsFromAttr(
  attr: DeviceDrawerAttr
): Array<{ id: string; name: string }> {
  if (!Array.isArray(attr.option)) return [];
  return attr.option
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as { id?: unknown; name?: unknown };
      if (row.id == null || row.id === '') return null;
      return {
        id: String(row.id),
        name: row.name == null || row.name === '' ? String(row.id) : String(row.name),
      };
    })
    .filter((item): item is { id: string; name: string } => item !== null);
}

export function formatDeviceAttrDisplay(
  attr: DeviceDrawerAttr,
  raw: unknown,
  labels?: { empty?: string; yes?: string; no?: string }
): string {
  const empty = labels?.empty ?? '--';
  if (raw === null || raw === undefined || raw === '') return empty;
  if (Array.isArray(raw) && raw.length === 0) return empty;
  if (attr.attr_type === 'pwd') return '***';
  if (attr.attr_type === 'bool') {
    const truthy = raw === true || raw === 'true' || raw === 1 || raw === '1';
    return truthy ? labels?.yes ?? 'Yes' : labels?.no ?? 'No';
  }
  if (attr.attr_type === 'enum') {
    const options = enumOptionsFromAttr(attr);
    const ids = Array.isArray(raw) ? raw : [raw];
    const names = ids.map((item) => {
      const hit = options.find((option) => option.id === String(item));
      return hit ? hit.name : String(item);
    });
    return names.length ? names.join('、') : empty;
  }
  if (Array.isArray(raw)) {
    return raw.map((item) => (item == null ? '' : String(item))).filter(Boolean).join('、') || empty;
  }
  if (typeof raw === 'object') {
    try {
      return JSON.stringify(raw);
    } catch {
      return empty;
    }
  }
  return String(raw);
}

export function buildDeviceDrawerRows(input: {
  attrs: DeviceDrawerAttr[] | null | undefined;
  detail: Record<string, unknown> | null | undefined;
  formatValue?: (attr: DeviceDrawerAttr, raw: unknown) => string;
}): DeviceDrawerRow[] {
  const listed = listDeviceDrawerAttrs(input.attrs);
  const format = input.formatValue || ((attr, raw) => formatDeviceAttrDisplay(attr, raw));
  if (listed.length) {
    return listed.map((attr) => ({
      key: attr.attr_id,
      label: attr.attr_name || attr.attr_id,
      value: format(attr, input.detail?.[attr.attr_id]),
    }));
  }
  if (!input.detail) return [];
  const skip = new Set<string>([
    ...DEVICE_DRAWER_HEADER_ATTR_IDS,
    'inst_id',
    'inst_uuid',
    'model_id',
    'overflow',
    'u_end',
    'permission',
  ]);
  return Object.keys(input.detail)
    .filter((key) => !skip.has(key) && !key.startsWith('_'))
    .map((key) => ({
      key,
      label: key,
      value: format({ attr_id: key, attr_name: key }, input.detail?.[key]),
    }));
}
