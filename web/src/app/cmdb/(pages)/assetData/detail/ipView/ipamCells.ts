export interface IpInstance {
  _id?: number | string;
  inst_uuid?: string;
  ip_addr: string;
  ip_status?: string[];
  ip_allocated_status?: string[];
  ip_type?: string[] | string;
  description?: string;
  inst_name?: string;
  permission?: string[];
  [key: string]: unknown;
}

export type AllocKind = 'free' | 'allocated' | 'reserved';
export type LiveKind = 'none' | 'online' | 'offline' | 'conflict';

export interface IpamLegendFilters {
  alloc: Record<AllocKind, boolean>;
  live: Record<Exclude<LiveKind, 'none'>, boolean>;
}

export const DEFAULT_IPAM_FILTERS: IpamLegendFilters = {
  alloc: { free: true, allocated: true, reserved: true },
  live: { online: true, offline: true, conflict: true },
};

export const ALLOC_COLOR: Record<AllocKind, string> = {
  free: '#52c41a',
  allocated: '#1677ff',
  reserved: '#faad14',
};

export const LIVE_COLOR: Record<Exclude<LiveKind, 'none'>, string> = {
  online: '#52c41a',
  offline: '#8c8c8c',
  conflict: '#ff4d4f',
};

function firstEnum(value: unknown): string | undefined {
  if (Array.isArray(value)) {
    return value.length ? String(value[0]) : undefined;
  }
  if (value == null || value === '') return undefined;
  return String(value);
}

export function classifyAlloc(ip: IpInstance | null): AllocKind {
  if (!ip) return 'free';
  const status = firstEnum(ip.ip_allocated_status);
  if (!status || status === 'available') return ip.ip_allocated_status ? 'free' : 'allocated';
  if (status === 'reserved') return 'reserved';
  if (status === 'allocated') return 'allocated';
  return 'allocated';
}

export function classifyLive(ip: IpInstance | null): LiveKind {
  if (!ip) return 'none';
  const statuses = ip.ip_status ?? [];
  if (statuses.includes('conflict')) return 'conflict';
  if (statuses.includes('online')) return 'online';
  if (statuses.includes('offline')) return 'offline';
  return 'none';
}

export function cellMatchesFilter(
  cell: { alloc: AllocKind; live: LiveKind },
  filters: IpamLegendFilters
): boolean {
  const allocOn = filters.alloc[cell.alloc];
  if (cell.live === 'none') return allocOn;
  return allocOn || filters.live[cell.live];
}

export function hostOctet(ipAddr: string): number {
  const parts = ipAddr.split('.');
  return parseInt(parts[parts.length - 1], 10);
}

export function buildOctetMap(ips: IpInstance[]): Map<number, IpInstance> {
  const map = new Map<number, IpInstance>();
  for (const ip of ips) {
    const oct = hostOctet(ip.ip_addr);
    if (!Number.isNaN(oct)) map.set(oct, ip);
  }
  return map;
}
