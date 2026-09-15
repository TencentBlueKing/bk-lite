export const EXECUTION_EXPORT_LIST_PAGE_SIZE = 100;
export const EXECUTION_EXPORT_MAX_TASKS = 500;
export const EXECUTION_EXPORT_MAX_RISK_DETAILS = 2000;
export const EXECUTION_EXPORT_RISK_DETAIL_CONCURRENCY = 4;

interface ExecutionExportPageParams {
  page: number;
  pageSize: number;
  signal?: AbortSignal;
}

interface ExecutionExportPage<T> {
  items: T[];
  count?: number;
}

interface CollectPagedItemsOptions<T> {
  fetchPage: (params: ExecutionExportPageParams) => Promise<ExecutionExportPage<T>>;
  pageSize?: number;
  maxItems?: number;
  signal?: AbortSignal;
}

interface CollectPagedItemsResult<T> {
  items: T[];
  truncated: boolean;
}

interface MapWithConcurrencyOptions<T, R> {
  items: readonly T[];
  mapper: (item: T, index: number, signal?: AbortSignal) => Promise<R>;
  concurrency?: number;
  maxResults?: number;
  signal?: AbortSignal;
}

interface MapWithConcurrencyResult<R> {
  items: R[];
  truncated: boolean;
}

const throwIfAborted = (signal?: AbortSignal) => {
  if (!signal?.aborted) return;
  const error = new Error('The operation was aborted.');
  error.name = 'AbortError';
  throw error;
};

export async function collectPagedItems<T>(
  options: CollectPagedItemsOptions<T>,
): Promise<CollectPagedItemsResult<T>> {
  const pageSize = options.pageSize ?? EXECUTION_EXPORT_LIST_PAGE_SIZE;
  const maxItems = options.maxItems ?? EXECUTION_EXPORT_MAX_TASKS;
  const items: T[] = [];
  let page = 1;
  let truncated = false;

  while (items.length < maxItems) {
    throwIfAborted(options.signal);
    const remaining = maxItems - items.length;
    const response = await options.fetchPage({
      page,
      pageSize,
      signal: options.signal,
    });
    const batch = response.items || [];
    if (batch.length === 0) break;

    items.push(...batch.slice(0, remaining));
    if (batch.length > remaining) {
      truncated = true;
      break;
    }
    if (typeof response.count === 'number' && items.length >= response.count) break;
    if (batch.length < pageSize) break;
    if (items.length >= maxItems) {
      truncated = typeof response.count === 'number'
        ? response.count > items.length
        : true;
      break;
    }
    page += 1;
  }

  return { items, truncated };
}

export async function mapWithConcurrency<T, R>(
  options: MapWithConcurrencyOptions<T, R>,
): Promise<MapWithConcurrencyResult<R>> {
  const concurrency = Math.max(1, options.concurrency ?? EXECUTION_EXPORT_RISK_DETAIL_CONCURRENCY);
  const maxResults = options.maxResults ?? EXECUTION_EXPORT_MAX_RISK_DETAILS;
  const limit = Math.min(options.items.length, maxResults);
  const truncated = options.items.length > limit;
  const results: R[] = [];
  let nextIndex = 0;
  const workerCount = Math.min(concurrency, limit);

  if (workerCount === 0) {
    return { items: results, truncated };
  }

  await Promise.all(Array.from({ length: workerCount }, async () => {
    while (true) {
      throwIfAborted(options.signal);
      const index = nextIndex;
      nextIndex += 1;
      if (index >= limit) return;
      results[index] = await options.mapper(options.items[index], index, options.signal);
    }
  }));

  return { items: results, truncated };
}
