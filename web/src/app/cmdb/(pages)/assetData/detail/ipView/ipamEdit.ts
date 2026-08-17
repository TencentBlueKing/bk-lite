export const IPAM_ALLOC_VALUES = ['available', 'allocated', 'reserved'] as const;

export type IpamAllocStatus = (typeof IPAM_ALLOC_VALUES)[number];

export type IpamEditAction = 'create' | 'update' | 'delete' | 'noop';

export const IPAM_ASSET_PERMISSION_PATH = '/cmdb/assetData';
export const IPAM_ALLOC_ATTR_ID = 'ip_allocated_status';
export const IPAM_STATUS_ATTR_ID = 'ip_status';
export const IPAM_TYPE_ATTR_ID = 'ip_type';
export const IPAM_USER_ATTR_ID = 'ip_user';
export const IPAM_MAC_ATTR_ID = 'mac';
export const IPAM_DESC_ATTR_ID = 'description';
export const IPAM_ADDR_ATTR_ID = 'ip_addr';
export const IPAM_AVAILABLE = 'available';
export const IPAM_ALLOCATED = 'allocated';

export const IPAM_EDITABLE_ATTR_IDS = [
  IPAM_ALLOC_ATTR_ID,
  IPAM_TYPE_ATTR_ID,
  IPAM_USER_ATTR_ID,
  IPAM_STATUS_ATTR_ID,
  IPAM_MAC_ATTR_ID,
  IPAM_DESC_ATTR_ID,
] as const;

export interface IpamEnumOption {
  id: string;
  name: string;
}

export interface IpamModelAttr {
  attr_id: string;
  attr_name?: string;
  attr_type?: string;
  option?: unknown;
  is_system_link?: boolean;
  is_display_field?: boolean;
}

const IPAM_HIDDEN_ATTR_IDS = new Set([
  'node_id',
  'monitor_id',
  'ip_table',
  'ip_table_display',
  IPAM_ADDR_ATTR_ID,
]);

export function firstEnum(value: unknown): string | undefined {
  if (Array.isArray(value)) {
    const first = value[0];
    return first == null || first === '' ? undefined : String(first);
  }
  if (value == null || value === '') {
    return undefined;
  }
  return String(value);
}

export function isIpamAllocStatus(value: unknown): value is IpamAllocStatus {
  return IPAM_ALLOC_VALUES.includes(value as IpamAllocStatus);
}

export function findModelAttr(
  attrs: IpamModelAttr[] | null | undefined,
  attrId: string
): IpamModelAttr | undefined {
  return (attrs || []).find((attr) => attr.attr_id === attrId);
}

export function enumOptionsFromAttr(attr: IpamModelAttr | null | undefined): IpamEnumOption[] {
  const option = attr?.option;
  if (!Array.isArray(option)) return [];
  return option
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as { id?: unknown; name?: unknown };
      if (row.id == null || row.id === '') return null;
      return {
        id: String(row.id),
        name: row.name == null || row.name === '' ? String(row.id) : String(row.name),
      };
    })
    .filter((item): item is IpamEnumOption => item !== null);
}

export function enumName(options: IpamEnumOption[], id: string | undefined): string | undefined {
  if (!id) return undefined;
  return options.find((item) => item.id === id)?.name;
}

export function defaultAllocStatus(options: IpamEnumOption[]): string {
  const allocated = options.find((item) => item.id === IPAM_ALLOCATED);
  if (allocated) return allocated.id;
  const claimed = options.find((item) => item.id !== IPAM_AVAILABLE);
  return claimed?.id || options[0]?.id || IPAM_ALLOCATED;
}

export function decideManualIpAction(input: {
  hasInstance: boolean;
  allocatedStatus: string;
}): IpamEditAction {
  if (!input.allocatedStatus) return 'noop';
  if (input.allocatedStatus === IPAM_AVAILABLE) {
    return input.hasInstance ? 'delete' : 'noop';
  }
  return input.hasInstance ? 'update' : 'create';
}

export function requiredMenuPermission(
  action: IpamEditAction
): 'Add' | 'Edit' | 'Delete' | null {
  if (action === 'create') return 'Add';
  if (action === 'update') return 'Edit';
  if (action === 'delete') return 'Delete';
  return null;
}

export function hasInstanceOperate(permission: unknown): boolean {
  if (permission == null) {
    return true;
  }
  return Array.isArray(permission) && permission.includes('Operate');
}

export function canPerformIpamEdit(input: {
  action: IpamEditAction;
  hasAdd: boolean;
  hasEdit: boolean;
  hasDelete: boolean;
  instOperate: boolean;
}): boolean {
  if (input.action === 'noop') return true;
  if (input.action === 'create') return input.hasAdd;
  if (input.action === 'update') return input.hasEdit && input.instOperate;
  return input.hasDelete && input.instOperate;
}

export function isPersistedIp(ip: { inst_uuid?: unknown; _id?: unknown } | null): boolean {
  if (!ip) return false;
  if (ip.inst_uuid) return true;
  return ip._id !== undefined && ip._id !== null && ip._id !== '';
}

export interface IpamEditPayload {
  subnet_inst_uuid: string;
  ip_addr: string;
  ip_allocated_status: string;
  ip_status?: string;
  ip_type?: string;
  ip_user?: string[];
  mac?: string;
  description?: string;
}

export function buildIpamEditPayload(input: {
  subnetInstUuid: string;
  ipAddr: string;
  allocatedStatus: string;
  ipStatus?: string;
  ipType?: string;
  ipUser?: string[];
  mac?: string;
  description?: string;
}): IpamEditPayload {
  return {
    subnet_inst_uuid: input.subnetInstUuid,
    ip_addr: input.ipAddr,
    ip_allocated_status: input.allocatedStatus,
    ip_status: input.ipStatus || '',
    ip_type: input.ipType || '',
    ip_user: input.ipUser || [],
    mac: input.mac || '',
    description: input.description || '',
  };
}

export function isEditableIpAttr(attrId: string): boolean {
  return (IPAM_EDITABLE_ATTR_IDS as readonly string[]).includes(attrId);
}

export function listDrawerIpAttrs(attrs: IpamModelAttr[] | null | undefined): IpamModelAttr[] {
  return (attrs || []).filter((attr) => {
    if (!attr?.attr_id) return false;
    if (attr.is_system_link || attr.is_display_field) return false;
    if (attr.attr_type === 'table') return false;
    if (IPAM_HIDDEN_ATTR_IDS.has(attr.attr_id)) return false;
    return true;
  });
}

export function listReadonlyIpAttrs(attrs: IpamModelAttr[] | null | undefined): IpamModelAttr[] {
  return listDrawerIpAttrs(attrs).filter((attr) => !isEditableIpAttr(attr.attr_id));
}

export function formatAttrDisplay(
  attr: IpamModelAttr,
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
    const names = ids.map((item) => enumName(options, String(item)) || String(item));
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
