import { TableDataItem } from '@/app/monitor/types';

/** 列表展示指标异步回填的单批实例数，需低于后端 _MAX_DISPLAY_METRICS_INSTANCE_IDS。 */
export const LIST_DISPLAY_METRIC_BATCH_SIZE = 10;

export function chunkInstanceIds(
  instanceIds: string[],
  batchSize = LIST_DISPLAY_METRIC_BATCH_SIZE
): string[][] {
  const size = Math.max(1, Math.floor(batchSize));
  const batches: string[][] = [];
  for (let index = 0; index < instanceIds.length; index += size) {
    batches.push(instanceIds.slice(index, index + size));
  }
  return batches;
}

export function mergeInstanceDisplayMetrics<T extends TableDataItem>(
  rows: T[],
  filled: Array<Record<string, unknown>>
): T[] {
  if (!rows.length || !filled.length) {
    return rows;
  }
  const byId = new Map<string, Record<string, unknown>>();
  for (const item of filled) {
    const instanceId = String(item.instance_id ?? '');
    if (instanceId) {
      byId.set(instanceId, item);
    }
  }
  return rows.map((row) => {
    const extra = byId.get(String(row.instance_id ?? ''));
    if (!extra) {
      return row;
    }
    const merged: TableDataItem = { ...row };
    Object.entries(extra).forEach(([key, value]) => {
      if (key !== 'instance_id') {
        merged[key] = value;
      }
    });
    return merged as T;
  });
}

function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false;
  }
  const name = 'name' in error ? String((error as { name?: unknown }).name || '') : '';
  return name === 'AbortError' || name === 'CancelledError';
}

export async function fillInstanceListDisplayMetrics<T extends TableDataItem>(options: {
  rows: T[];
  fetchBatch: (
    instanceIds: string[],
    signal?: AbortSignal
  ) => Promise<Array<Record<string, unknown>>>;
  signal?: AbortSignal;
  batchSize?: number;
  isCurrent?: () => boolean;
}): Promise<T[]> {
  const { rows, fetchBatch, signal, isCurrent } = options;
  const instanceIds = rows
    .map((row) => String(row.instance_id ?? ''))
    .filter(Boolean);
  if (!instanceIds.length) {
    return rows;
  }
  const batches = chunkInstanceIds(instanceIds, options.batchSize);
  const filledBatches = await Promise.all(
    batches.map(async (batch) => {
      if (signal?.aborted || isCurrent?.() === false) {
        return [] as Array<Record<string, unknown>>;
      }
      try {
        return (await fetchBatch(batch, signal)) || [];
      } catch (error) {
        if (isAbortError(error) || signal?.aborted) {
          return [] as Array<Record<string, unknown>>;
        }
        return [] as Array<Record<string, unknown>>;
      }
    })
  );
  if (signal?.aborted || isCurrent?.() === false) {
    return rows;
  }
  return mergeInstanceDisplayMetrics(rows, filledBatches.flat());
}
