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

export type CellKind =
  | 'free'
  | 'allocated_online'
  | 'allocated_offline'
  | 'conflict'
  | 'reserved'
  | 'gateway'
  | 'unknown';

export const KIND_COLOR: Record<CellKind, string> = {
  free: '#52c41a',
  allocated_online: '#1677ff',
  allocated_offline: '#8c8c8c',
  conflict: '#ff4d4f',
  reserved: '#faad14',
  gateway: '#722ed1',
  unknown: '#bfbfbf',
};

export function ipToCellKind(ip: IpInstance): CellKind {
  const statuses = ip.ip_status ?? [];
  const allocStatuses = ip.ip_allocated_status ?? [];
  const ipType = ip.ip_type
    ? Array.isArray(ip.ip_type)
      ? ip.ip_type
      : [String(ip.ip_type)]
    : [];

  if (statuses.includes('conflict')) return 'conflict';
  if (allocStatuses.includes('reserved')) return 'reserved';
  if (ipType.includes('gateway')) return 'gateway';

  const isOnline = statuses.includes('online');
  const isOffline = statuses.includes('offline');
  const isAllocated = allocStatuses.includes('allocated');

  if (isAllocated && isOnline) return 'allocated_online';
  if (isAllocated && isOffline) return 'allocated_offline';
  if (isAllocated) return 'allocated_online';

  if (statuses.includes('unknown') || allocStatuses.includes('unknown')) return 'unknown';

  return 'unknown';
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
