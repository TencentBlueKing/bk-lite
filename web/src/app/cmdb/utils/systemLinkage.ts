import type { ClientData } from '@/types';
import { hasAppAccess } from '@/context/appCapabilities/access';
import { HandledRequestError } from '@/utils/request';

export const MONITOR_SYNC_MODEL_IDS = new Set([
  'host',
  'switch',
  'router',
  'firewall',
  'loadbalance',
  'physcial_server',
  'mysql',
  'postgresql',
  'mssql',
  'influxdb',
  'oracle',
  'redis',
  'mongodb',
  'es',
  'apache',
  'tomcat',
  'nginx',
  'rabbitmq',
  'kafka',
  'zookeeper',
  'activemq',
  'minio',
  'etcd',
  'haproxy',
  'docker',
]);

export const showNodeId = (modelId: string) => modelId === 'host';

export const canSyncMonitor = (modelId: string) => MONITOR_SYNC_MODEL_IDS.has(modelId);

const PLATFORM_MODEL_IDS = new Set([
  'k8s_cluster',
  'k8s_namespace',
  'k8s_workload',
  'k8s_pod',
  'k8s_node',
  'vmware_vc',
  'aliyun_account',
  'qcloud',
  'hwcloud',
  'fusioninsight',
]);
const PLATFORM_MODEL_PREFIXES = [
  'k8s_',
  'aliyun',
  'qcloud',
  'hwcloud',
  'vmware_',
  'fusioninsight',
];

export const isPlatformTreeModel = (modelId: string) => {
  const text = String(modelId || '').trim();
  if (!text) return false;
  if (PLATFORM_MODEL_IDS.has(text)) return true;
  return PLATFORM_MODEL_PREFIXES.some((prefix) => text.startsWith(prefix));
};

export const canOpenMonitorLink = (
  clientData: ClientData[] | undefined | null,
  clientLoading: boolean,
  modelId: string,
) => {
  if (clientLoading) return false;
  if (!hasAppAccess(clientData, 'cmdb')) return false;
  if (!hasAppAccess(clientData, 'monitor')) return false;
  return !isPlatformTreeModel(modelId);
};

const MONITOR_OBJECT_TO_CMDB_MODEL: Record<string, string> = {
  Host: 'host',
  Switch: 'switch',
  Router: 'router',
  Firewall: 'firewall',
  Loadbalance: 'loadbalance',
  'Hardware Server': 'physcial_server',
  Mysql: 'mysql',
  Postgres: 'postgresql',
  MSSQL: 'mssql',
  InfluxDB: 'influxdb',
  Oracle: 'oracle',
  Redis: 'redis',
  MongoDB: 'mongodb',
  ElasticSearch: 'es',
  Apache: 'apache',
  Tomcat: 'tomcat',
  Nginx: 'nginx',
  RabbitMQ: 'rabbitmq',
  Kafka: 'kafka',
  Zookeeper: 'zookeeper',
  ActiveMQ: 'activemq',
  Minio: 'minio',
  Etcd: 'etcd',
  Haproxy: 'haproxy',
  'Docker Container': 'docker',
};

export const builtinCmdbModelId = (objectName: string) => {
  const text = String(objectName || '').trim();
  if (!text) return null;
  return MONITOR_OBJECT_TO_CMDB_MODEL[text] || null;
};

export const canOpenCmdbLink = (
  clientData: ClientData[] | undefined | null,
  clientLoading: boolean,
  objectName: string,
) => {
  if (clientLoading) return false;
  if (!hasAppAccess(clientData, 'cmdb')) return false;
  if (!hasAppAccess(clientData, 'monitor')) return false;
  const modelId = builtinCmdbModelId(objectName);
  if (!modelId) return false;
  return !isPlatformTreeModel(modelId);
};

export const EXTERNAL_ID_COLUMN_KEY = 'external_id';
export const EXTERNAL_ID_EMPTY = '--';
const SYSTEM_LINK_ATTR_IDS = new Set(['node_id', 'monitor_id']);

export const isSystemLinkAttr = (attr: {
  attr_id?: string;
  is_system_link?: unknown;
}) => Boolean(attr.is_system_link) || SYSTEM_LINK_ATTR_IDS.has(String(attr.attr_id || ''));

export const isSystemLinkAttrId = (key: string) => SYSTEM_LINK_ATTR_IDS.has(key);

export const resolveListDisplayFieldKeys = (
  saved: string[] | undefined | null,
  attrList: { attr_id: string; is_system_link?: unknown }[],
) => {
  if (Array.isArray(saved)) {
    return saved.filter((key) => !isSystemLinkAttrId(key));
  }
  return attrList
    .filter((item) => !isSystemLinkAttr(item))
    .map((item) => item.attr_id);
};

export type ExternalIdLineKey = 'node_id' | 'monitor_id';

export interface ExternalIdLine {
  key: ExternalIdLineKey;
  value: string;
}

const asLinkId = (value: unknown) =>
  typeof value === 'string' ? value.trim() : value == null || value === '' ? '' : String(value).trim();

export const buildExternalIdLines = (
  modelId: string,
  record: { node_id?: unknown; monitor_id?: unknown },
): ExternalIdLine[] => {
  const monitor = { key: 'monitor_id' as const, value: asLinkId(record.monitor_id) };
  if (showNodeId(modelId)) {
    return [
      { key: 'node_id', value: asLinkId(record.node_id) },
      monitor,
    ];
  }
  return [monitor];
};

export const displayExternalIdValue = (value: string) => value || EXTERNAL_ID_EMPTY;

export const isMonitorSold = (clientData: ClientData[] | undefined | null) => {
  if (!clientData?.length) return true;
  return clientData.some((item) => item.name === 'monitor');
};

export interface MonitorLinkPayload {
  link_status?: string;
}

export const resolveMonitorLinkMessage = (payload: MonitorLinkPayload | null | undefined) => {
  const status = payload?.link_status;
  if (status === 'ok') return 'Model.systemLinkageSyncOk';
  if (status === 'not_found') return 'Model.systemLinkageSyncNotFound';
  if (status === 'conflict') return 'Model.systemLinkageSyncConflict';
  return 'Model.systemLinkageSyncFailed';
};

export interface BatchPushSummary {
  total?: number;
  ok?: number;
  already_linked?: number;
  not_found?: number;
  conflict?: number;
  failed?: number;
  skipped_model?: number;
}

export type BatchPushMessageLevel = 'success' | 'warning' | 'error';

const toCount = (value: unknown) => {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
};

export const pickBatchPushCounts = (summary: BatchPushSummary | null | undefined) => {
  const failed = toCount(summary?.failed) + toCount(summary?.skipped_model);
  return {
    ok: toCount(summary?.ok),
    already_linked: toCount(summary?.already_linked),
    not_found: toCount(summary?.not_found),
    conflict: toCount(summary?.conflict),
    failed,
  };
};

export const resolveBatchPushSummaryLevel = (
  summary: BatchPushSummary | null | undefined
): BatchPushMessageLevel => {
  const counts = pickBatchPushCounts(summary);
  const good = counts.ok + counts.already_linked;
  const problem = counts.not_found + counts.conflict + counts.failed;
  if (good > 0 && problem === 0) return 'success';
  if (good > 0 && problem > 0) return 'warning';
  return 'error';
};

export interface MonitorBindCandidate {
  id: string;
  name: string;
  ip?: string | null;
  object_name?: string | null;
  cmdb_id?: string | null;
}

export interface MonitorBindConflict {
  status?: string;
  occupiedLabel?: string;
}

const asRecord = (value: unknown): Record<string, unknown> | undefined =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;

const asTrimmedString = (value: unknown): string =>
  typeof value === 'string' ? value.trim() : '';

export const parseMonitorBindConflict = (error: unknown): MonitorBindConflict => {
  if (!(error instanceof HandledRequestError)) {
    return {};
  }
  const data = asRecord(asRecord(error.payload)?.data);
  const occupiedLabel =
    asTrimmedString(data?.occupied_inst_name) ||
    asTrimmedString(data?.occupied_inst_uuid) ||
    undefined;
  return {
    status: typeof data?.status === 'string' ? data.status : undefined,
    occupiedLabel,
  };
};
