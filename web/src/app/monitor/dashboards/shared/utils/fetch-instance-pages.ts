import {
  DASHBOARD_INSTANCE_SELECTOR_MAX_ITEMS,
  DASHBOARD_INSTANCE_SELECTOR_PAGE_SIZE
} from './constants';

type InstanceListResponse = {
  count?: number;
  results?: unknown[];
};

type GetInstanceList = (
  objectId: string | number,
  params: { page: number; page_size: number }
) => Promise<InstanceListResponse>;

/**
 * 分页拉取仪表盘实例选择器数据，替代 page_size=-1。
 * 达到 MAX_ITEMS 仍有更多时 truncated=true，避免静默只拿第一页。
 */
export async function fetchDashboardInstancePages(
  getInstanceList: GetInstanceList,
  monitorObjectId: string | number
): Promise<{ results: unknown[]; truncated: boolean; total: number }> {
  const pageSize = DASHBOARD_INSTANCE_SELECTOR_PAGE_SIZE;
  const maxItems = DASHBOARD_INSTANCE_SELECTOR_MAX_ITEMS;
  const results: unknown[] = [];
  let page = 1;
  let total = 0;

  while (results.length < maxItems) {
    const data = await getInstanceList(monitorObjectId, {
      page,
      page_size: pageSize
    });
    const batch = Array.isArray(data?.results) ? data.results : [];
    total = typeof data?.count === 'number' ? data.count : results.length + batch.length;
    results.push(...batch);
    if (batch.length < pageSize || results.length >= total) {
      break;
    }
    page += 1;
  }

  const truncated = total > results.length || results.length > maxItems;
  return {
    results: results.slice(0, maxItems),
    truncated: truncated || (results.length >= maxItems && total > maxItems),
    total
  };
}
