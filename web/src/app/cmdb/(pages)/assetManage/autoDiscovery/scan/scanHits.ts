export interface ScanExecutionSummary {
  id: number;
  status: string;
  target_count: number;
  received_count: number;
}

export interface ScanHitItem {
  id: number;
  host: string;
  protocol: string;
  family_model_id?: string;
  status: string;
  soid: string;
  cmdb_model_id: string;
  credential_id: string;
  credential_label?: string;
  inst_uuid: string;
  port?: number;
  unmatch_reason?: string;
  snapshot?: Record<string, unknown>;
  confidence?: 'low' | 'medium' | 'high' | string;
  evidence?: string[];
}

export const TERMINAL_STATUSES = new Set(['completed', 'failed', 'timed_out']);
export const SCAN_CONFIDENCE_LEVELS = ['high', 'medium', 'low'] as const;
export type ScanConfidenceLevel = (typeof SCAN_CONFIDENCE_LEVELS)[number];
export const DEFAULT_SCAN_CONFIDENCE_FILTER: ScanConfidenceLevel[] = ['high', 'medium'];

export const hitConfidence = (hit: ScanHitItem): ScanConfidenceLevel => {
  const value = String(hit.confidence || 'low');
  if (value === 'high' || value === 'medium' || value === 'low') {
    return value;
  }
  return 'low';
};

export const countHitsByConfidence = (hits: ScanHitItem[]) => {
  const counts: Record<ScanConfidenceLevel, number> = { high: 0, medium: 0, low: 0 };
  hits.forEach((hit) => {
    counts[hitConfidence(hit)] += 1;
  });
  return counts;
};

export const filterHitsByConfidence = (hits: ScanHitItem[], selected: Iterable<string>) => {
  const wanted = new Set(selected);
  if (wanted.size === 0) {
    return [];
  }
  return hits.filter((hit) => wanted.has(hitConfidence(hit)));
};
export const HIT_FETCH_SIZE = 200;
export const TABLE_PAGE_SIZE = 20;
export const GROUP_PAGE_SIZE = 10;
export const SOID_LIBRARY_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/soid';
export const PORT_LIBRARY_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/port';
export const SCAN_PERMISSION_PATH = '/cmdb/assetManage/autoDiscovery/collection';
export const EMPTY_SOID_KEY = '__empty_soid__';

export const SCAN_MIDDLEWARE_TYPES = [
  'nginx',
  'tomcat',
  'kafka',
  'zookeeper',
  'rabbitmq',
  'consul',
  'etcd',
] as const;

const SCAN_MIDDLEWARE_TYPE_SET = new Set<string>(SCAN_MIDDLEWARE_TYPES);

export const SCAN_DATABASE_TYPES = ['mysql', 'postgresql', 'mssql'] as const;
const SCAN_DATABASE_TYPE_SET = new Set<string>(SCAN_DATABASE_TYPES);

export const isScanMiddlewareType = (modelId?: string) => Boolean(modelId && SCAN_MIDDLEWARE_TYPE_SET.has(modelId));

export const isScanDatabaseType = (modelId?: string) => Boolean(modelId && SCAN_DATABASE_TYPE_SET.has(modelId));

export const isScanLinkMonitorType = (hit: ScanHitItem) => {
  const family = hit.family_model_id || hit.protocol;
  return isScanMiddlewareType(family) || isScanDatabaseType(family) || isScanMiddlewareType(hit.cmdb_model_id) || isScanDatabaseType(hit.cmdb_model_id);
};

export const hitHasCollectCredential = (hit: ScanHitItem) => Boolean(String(hit.credential_id || '').trim());

export const hitHasCmdbInstance = (hit: ScanHitItem) => Boolean(String(hit.inst_uuid || '').trim());

export const isLinkMonitorFamilyTab = (familyTab?: string) =>
  familyTab === 'middleware' ||
  familyTab === 'database' ||
  isScanMiddlewareType(familyTab) ||
  isScanDatabaseType(familyTab);

const FAMILY_ORDER = [
  'network',
  'host',
  'middleware',
  'nginx',
  'tomcat',
  'kafka',
  'zookeeper',
  'rabbitmq',
  'consul',
  'etcd',
  'physcial_server',
  'database',
  'mysql',
  'postgresql',
  'mssql',
  'influxdb',
];

export const displayValue = (value: unknown) => {
  if (value === null || value === undefined || value === '') {
    return '--';
  }
  return String(value);
};

export const snapshotText = (hit: ScanHitItem, keys: string[]) => {
  const snapshot = hit.snapshot || {};
  for (const key of keys) {
    const value = snapshot[key];
    if (value !== null && value !== undefined && value !== '') {
      return String(value);
    }
  }
  return '--';
};

export const hitSoid = (hit: ScanHitItem) => {
  const fromField = String(hit.soid || '').trim();
  if (fromField) {
    return fromField;
  }
  const snapshot = hit.snapshot || {};
  for (const key of ['soid', 'sysobjectid', 'sysObjectID']) {
    const value = snapshot[key];
    if (value !== null && value !== undefined && value !== '') {
      return String(value).trim();
    }
  }
  return '';
};

export const oidLibraryUrl = (soid: string) => `${SOID_LIBRARY_PATH}?oid=${encodeURIComponent(soid)}`;
export const portLibraryUrl = (targetType: string) =>
  `${PORT_LIBRARY_PATH}?type=${encodeURIComponent(targetType)}`;

export const sortedMatchedFamilies = (hits: ScanHitItem[]) => {
  const present = new Set(hits.map((hit) => hit.family_model_id || hit.protocol || 'unknown'));
  return [...present].sort((a, b) => {
    const ai = FAMILY_ORDER.indexOf(a);
    const bi = FAMILY_ORDER.indexOf(b);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });
};

export const groupNetworkUnmatchedBySoid = (hits: ScanHitItem[]) => {
  const grouped = new Map<string, ScanHitItem[]>();
  hits.forEach((hit) => {
    const key = hitSoid(hit) || EMPTY_SOID_KEY;
    const list = grouped.get(key) || [];
    list.push(hit);
    grouped.set(key, list);
  });
  return [...grouped.entries()]
    .sort((a, b) => {
      if (a[0] === EMPTY_SOID_KEY) return 1;
      if (b[0] === EMPTY_SOID_KEY) return -1;
      return b[1].length - a[1].length;
    })
    .map(([soid, groupHits]) => ({ soid, hits: groupHits }));
};

export const groupDbUnmatchedByFamily = (hits: ScanHitItem[]) => {
  const grouped = new Map<string, ScanHitItem[]>();
  hits.forEach((hit) => {
    const key = hit.family_model_id || hit.protocol || 'database';
    const list = grouped.get(key) || [];
    list.push(hit);
    grouped.set(key, list);
  });
  return [...grouped.entries()]
    .sort((a, b) => b[1].length - a[1].length)
    .map(([familyModelId, groupHits]) => ({ familyModelId, hits: groupHits }));
};
