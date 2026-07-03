export interface CollectDetectFingerprintInput {
  monitorPluginId: number;
  monitorObjectId: number;
  nodeId: unknown;
  instance: Record<string, unknown>;
}

export interface CollectDetectTaskLike {
  status: 'pending' | 'running' | 'success' | 'failed';
}

export type CollectDetectPresentationTone = 'processing' | 'success' | 'error';

export const stableStringify = (value: unknown): string => {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify((value as Record<string, unknown>)[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value) ?? 'null';
};

export const buildCollectDetectFingerprint = ({
  monitorPluginId,
  monitorObjectId,
  nodeId,
  instance,
}: CollectDetectFingerprintInput) =>
  stableStringify({
    monitor_plugin_id: monitorPluginId,
    monitor_object_id: monitorObjectId,
    node_id: nodeId,
    instance,
  });

export const shouldAcceptCollectDetectResult = (
  task: { rowKey: string; fingerprint: string },
  activeFingerprints: Record<string, string>
) => activeFingerprints[task.rowKey] === task.fingerprint;

export const getRowsForBatchCollectDetect = <T extends { key?: unknown }>(
  rows: T[],
  selectedRowKeys: unknown[]
) => {
  const selected = new Set(selectedRowKeys.map(String));
  return rows.filter((row) => row.key !== undefined && selected.has(String(row.key)));
};

export const getCollectDetectResultPresentation = (
  task: CollectDetectTaskLike
): { tone: CollectDetectPresentationTone; titleKey: string } => {
  if (task.status === 'success') {
    return {
      tone: 'success',
      titleKey: 'monitor.integrations.collectDetectSuccess',
    };
  }
  if (task.status === 'failed') {
    return {
      tone: 'error',
      titleKey: 'monitor.integrations.collectDetectFailed',
    };
  }
  return {
    tone: 'processing',
    titleKey: 'monitor.integrations.collectDetectRunning',
  };
};
