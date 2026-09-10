export interface CollectorRetryRowIdentity {
  node_id?: string | number;
}

export function readCollectorRetryTaskId(payload: unknown): string | null {
  if (payload === null || payload === undefined || typeof payload !== 'object') {
    return null;
  }
  if (!('task_id' in payload)) {
    return null;
  }
  const taskId = payload.task_id;
  if (typeof taskId === 'number' && Number.isFinite(taskId)) {
    return String(taskId);
  }
  if (typeof taskId === 'string') {
    const trimmed = taskId.trim();
    return trimmed === '' ? null : trimmed;
  }
  return null;
}

export function mergeCollectorRetryRows<T extends CollectorRetryRowIdentity>(
  currentRows: T[],
  retryRows: T[],
): T[] {
  if (retryRows.length === 0) {
    return currentRows;
  }

  const retryByNodeId = new Map<string, T>();
  for (const row of retryRows) {
    if (row.node_id === undefined || row.node_id === null || row.node_id === '') {
      continue;
    }
    retryByNodeId.set(String(row.node_id), row);
  }
  if (retryByNodeId.size === 0) {
    return currentRows;
  }

  return currentRows.map((row) => {
    if (row.node_id === undefined || row.node_id === null || row.node_id === '') {
      return row;
    }
    const overlay = retryByNodeId.get(String(row.node_id));
    return overlay ? { ...row, ...overlay } : row;
  });
}
