import type { MetricItem } from '@/app/monitor/types';
import type {
  MetricCatalogGroup,
  MetricCatalogPage,
  MetricsParam
} from './index';

export const METRIC_CATALOG_PAGE_SIZE = 100;
/** 选择器累计上限：避免异常大目录拖垮页面。 */
export const METRIC_CATALOG_MAX_ITEMS = 5000;

type GetCatalogPage<T> = (
  params?: MetricsParam,
  config?: unknown
) => Promise<MetricCatalogPage<T>>;

async function fetchAllCatalogPages<T>(
  getPage: GetCatalogPage<T>,
  params: MetricsParam = {},
  config?: unknown
): Promise<{ items: T[]; truncated: boolean; total: number }> {
  const pageSize = METRIC_CATALOG_PAGE_SIZE;
  const maxItems = METRIC_CATALOG_MAX_ITEMS;
  const items: T[] = [];
  let page = 1;
  let total = 0;

  while (items.length < maxItems) {
    const data = await getPage(
      {
        ...params,
        page,
        page_size: pageSize
      },
      config
    );
    const batch = Array.isArray(data?.items) ? data.items : [];
    total = typeof data?.count === 'number' ? data.count : items.length + batch.length;
    items.push(...batch);
    if (batch.length < pageSize || items.length >= total) {
      break;
    }
    page += 1;
  }

  return {
    items: items.slice(0, maxItems),
    truncated: total > Math.min(items.length, maxItems),
    total
  };
}

/**
 * 分页累加拉取指标目录，替代单次 page_size=-1（后端 max_page_size=100）。
 */
export async function fetchAllMonitorMetrics(
  getMonitorMetrics: GetCatalogPage<MetricItem>,
  params: MetricsParam = {},
  config?: unknown
) {
  return fetchAllCatalogPages(getMonitorMetrics, params, config);
}

/** 分页累加拉取指标分组，保证选择器能挂上全部指标。 */
export async function fetchAllMetricsGroups(
  getMetricsGroup: GetCatalogPage<MetricCatalogGroup>,
  params: MetricsParam = {},
  config?: unknown
) {
  return fetchAllCatalogPages(getMetricsGroup, params, config);
}
