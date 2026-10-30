/** 选择主机时的筛选。host.os_type 枚举：1 Linux，2 Windows，3 AIX，4 Unix。 */

export interface HostQueryCondition {
  field: string;
  type: string;
  value: unknown;
}

export interface HostPickerFilter {
  instName?: string;
  ip?: string;
  osType?: string;
}

export const HOST_OS_OPTIONS = [
  { value: '1', label: 'Linux' },
  { value: '2', label: 'Windows' },
  { value: '3', label: 'AIX' },
  { value: '4', label: 'Unix' },
  { value: 'other', label: 'Other' },
];

export function formatHostOsType(value: unknown) {
  const text = String(value ?? '').trim();
  if (!text) {
    return '--';
  }
  const matched = HOST_OS_OPTIONS.find(
    (item) => item.value === text || item.label.toLowerCase() === text.toLowerCase()
  );
  return matched?.label || text;
}

export function buildHostPickerQuery(
  existing: HostQueryCondition[] | undefined,
  filter: HostPickerFilter
) {
  const query = [...(existing || [])];
  const instName = filter.instName?.trim();
  const ip = filter.ip?.trim();
  if (instName) {
    query.push({ field: 'inst_name', type: 'str*', value: instName });
  }
  if (ip) {
    query.push({ field: 'ip_addr', type: 'str*', value: ip });
  }
  if (filter.osType) {
    query.push({ field: 'os_type', type: 'list_any[]', value: [filter.osType] });
  }
  return query;
}
