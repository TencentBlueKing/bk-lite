import {
  DASHBOARD_INSTANCE_SELECTOR_MAX_ITEMS,
  DASHBOARD_INSTANCE_SELECTOR_PAGE_SIZE,
} from './constants';
import { fetchMonitorInstancePages } from '@/app/monitor/utils/fetchInstancePages';

interface InstanceListResponse {
  count?: number;
  results?: unknown[];
}

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
  return fetchMonitorInstancePages(getInstanceList, monitorObjectId, {}, {
    pageSize: DASHBOARD_INSTANCE_SELECTOR_PAGE_SIZE,
    maxItems: DASHBOARD_INSTANCE_SELECTOR_MAX_ITEMS,
  });
}
