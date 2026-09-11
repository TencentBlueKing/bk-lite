import type { ClientData } from '@/types';
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
