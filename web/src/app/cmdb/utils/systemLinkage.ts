import type { ClientData } from '@/types';

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
