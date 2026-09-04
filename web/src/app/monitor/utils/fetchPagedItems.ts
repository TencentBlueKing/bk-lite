/** 监控列表有界分页默认页大小（替代 page_size=-1）。 */
export const MONITOR_LIST_PAGE_SIZE = 500;
/** 监控列表有界分页累计上限。 */
export const MONITOR_LIST_MAX_ITEMS = 2000;

export interface PagedFetchResult<T> {
  items: T[];
  truncated: boolean;
  total: number;
}

type FetchPageFn<T> = (
  page: number,
  pageSize: number
) => Promise<{ items: T[]; total?: number }>;

/**
 * 通用有界分页累加：禁止 page_size=-1，达到 maxItems 后截断并标记 truncated。
 */
export async function fetchPagedItems<T>(
  fetchPage: FetchPageFn<T>,
  options?: { pageSize?: number; maxItems?: number }
): Promise<PagedFetchResult<T>> {
  const pageSize = options?.pageSize ?? MONITOR_LIST_PAGE_SIZE;
  const maxItems = options?.maxItems ?? MONITOR_LIST_MAX_ITEMS;
  const items: T[] = [];
  let page = 1;
  let total = 0;

  while (items.length < maxItems) {
    const data = await fetchPage(page, pageSize);
    const batch = Array.isArray(data.items) ? data.items : [];
    total =
      typeof data.total === 'number'
        ? data.total
        : items.length + batch.length;
    items.push(...batch);
    if (batch.length < pageSize || items.length >= total) {
      break;
    }
    page += 1;
  }

  const sliced = items.slice(0, maxItems);
  const truncated =
    total > sliced.length ||
    items.length > maxItems ||
    (sliced.length >= maxItems && total > maxItems);

  return {
    items: sliced,
    truncated,
    total,
  };
}
