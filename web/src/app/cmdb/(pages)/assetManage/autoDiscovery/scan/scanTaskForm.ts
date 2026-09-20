const SSH_SECRET_KEYS = ['username', 'password', 'key', 'private_key'] as const;
const SNMP_VERSIONS = new Set(['v2', 'v2c', 'v3']);

export const poolHasSshSecret = (pool: Array<Record<string, unknown>> | undefined = []) =>
  pool.some((item) =>
    SSH_SECRET_KEYS.some((key) => {
      const value = item?.[key];
      return value !== undefined && value !== null && String(value).trim() !== '';
    })
  );

export const withDefaultSnmpVersion = <T extends Record<string, unknown>>(item: T): T => {
  const version = String(item?.version ?? '').trim();
  if (SNMP_VERSIONS.has(version)) {
    return item;
  }
  const community = String(item?.community ?? '').trim();
  const username = String(item?.username ?? '').trim();
  return {
    ...item,
    version: username && !community ? 'v3' : 'v2',
  };
};

export const withDefaultSnmpPool = <T extends Record<string, unknown>>(pool: T[] | undefined = []) =>
  pool.map((item) => withDefaultSnmpVersion(item));

export interface ScanAccessPointOption {
  label: string;
  value: string;
  origin: Record<string, unknown>;
}

export interface ScanTaskDetail {
  name?: string;
  team?: unknown;
  ip_ranges?: Array<{ begin?: string; end?: string }>;
  families?: string[];
  credentials?: Record<string, unknown>;
  access_point?: Array<{ id?: string } & Record<string, unknown>>;
  timeout?: number;
  cloud_region?: unknown;
}

const emptyRange = { begin: '', end: '' };

const withDefaultScanCredentials = (credentials: Record<string, unknown>) => {
  const network = credentials.network;
  if (!Array.isArray(network)) {
    return credentials;
  }
  return {
    ...credentials,
    network: withDefaultSnmpPool(network as Array<Record<string, unknown>>),
  };
};

export const mapScanDetailToFormValues = (detail: ScanTaskDetail) => ({
  name: detail.name,
  team: detail.team,
  ipRanges: detail.ip_ranges?.length ? detail.ip_ranges : [emptyRange],
  families: detail.families || [],
  credentials: withDefaultScanCredentials(detail.credentials || {}),
  accessPointId: detail.access_point?.[0]?.id,
  timeout: detail.timeout ?? 0,
});

export const resolveAccessPointOrigin = (
  accessPoints: ScanAccessPointOption[],
  accessPointId: string | undefined,
  fallback?: Record<string, unknown> | null
) => accessPoints.find((item) => item.value === accessPointId)?.origin || fallback || {};

export const cloudRegionFromOrigin = (origin: Record<string, unknown>) => {
  const nested = origin.cloud_region;
  if (typeof nested === 'number' || (typeof nested === 'string' && nested !== '')) {
    return {
      id: nested,
      name: origin.cloud_region_name ?? origin.cloud_name ?? '',
    };
  }
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    const region = nested as Record<string, unknown>;
    const id = region.id ?? region.cloud_region_id ?? region.cloud;
    if (id !== undefined && id !== null && id !== '') {
      return {
        id,
        name: region.name ?? region.cloud_region_name ?? region.cloud_name ?? '',
      };
    }
  }
  const id = origin.cloud_region_id ?? origin.cloud;
  if (id === undefined || id === null || id === '') {
    return null;
  }
  return {
    id,
    name: origin.cloud_region_name ?? origin.cloud_name ?? '',
  };
};

export const hasScanCloudRegion = (value: unknown) => {
  if (value === null || value === undefined || value === '') {
    return false;
  }
  if (typeof value === 'number' || typeof value === 'string') {
    return true;
  }
  if (typeof value === 'object' && !Array.isArray(value)) {
    const id = (value as Record<string, unknown>).id;
    return id !== undefined && id !== null && id !== '';
  }
  return false;
};

export const resolveScanCloudRegion = ({
  includeCloudRegion,
  origin,
  existing,
}: {
  includeCloudRegion: boolean;
  origin: Record<string, unknown>;
  existing?: unknown;
}) => {
  if (!includeCloudRegion) {
    return {};
  }
  return cloudRegionFromOrigin(origin) ?? existing ?? null;
};

export const buildScanTaskSubmitMeta = ({
  accessPointId,
  accessPoints,
  fallbackAccessPoint,
  includeCloudRegion,
  existingCloudRegion,
  timeout,
}: {
  accessPointId?: string;
  accessPoints: ScanAccessPointOption[];
  fallbackAccessPoint?: Record<string, unknown> | null;
  includeCloudRegion: boolean;
  existingCloudRegion?: unknown;
  timeout?: number | null;
}) => {
  const origin = resolveAccessPointOrigin(accessPoints, accessPointId, fallbackAccessPoint);
  return {
    origin,
    access_point: accessPointId ? [origin] : [],
    timeout: timeout ?? 0,
    cloud_region: resolveScanCloudRegion({
      includeCloudRegion,
      origin,
      existing: existingCloudRegion,
    }),
  };
};
