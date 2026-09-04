import {
  fetchPagedItems,
  MONITOR_LIST_MAX_ITEMS,
  MONITOR_LIST_PAGE_SIZE,
} from '@/app/monitor/utils/fetchPagedItems';

interface InstanceListResponse {
  count?: number;
  results?: unknown[];
}

type MonitorObjectId = string | number | React.Key;

type GetInstanceList = (
  objectId: MonitorObjectId,
  params: Record<string, unknown>
) => Promise<InstanceListResponse>;

export interface FetchMonitorInstancePagesResult {
  results: unknown[];
  truncated: boolean;
  total: number;
}

/**
 * 分页拉取监控实例列表，替代 page_size=-1。
 * 达到 maxItems 仍有更多时 truncated=true。
 */
export async function fetchMonitorInstancePages(
  getInstanceList: GetInstanceList,
  monitorObjectId: MonitorObjectId,
  extraParams: Record<string, unknown> = {},
  options?: { pageSize?: number; maxItems?: number }
): Promise<FetchMonitorInstancePagesResult> {
  const pageSize = options?.pageSize ?? MONITOR_LIST_PAGE_SIZE;
  const maxItems = options?.maxItems ?? MONITOR_LIST_MAX_ITEMS;

  const { items, truncated, total } = await fetchPagedItems<unknown>(
    async (page, size) => {
      const data = await getInstanceList(monitorObjectId, {
        ...extraParams,
        page,
        page_size: size,
      });
      return {
        items: Array.isArray(data?.results) ? data.results : [],
        total: typeof data?.count === 'number' ? data.count : undefined,
      };
    },
    { pageSize, maxItems }
  );

  return { results: items, truncated, total };
}
