export const PENDING_RISK_EXPORT_PAGE_SIZE = 100;
/** 浏览器同步导出上限：约 50 页，避免一次拉全量拖垮页面。 */
export const PENDING_RISK_EXPORT_MAX_ROWS = 5000;

export type PendingRiskView = 'host' | 'patch' | 'baseline';

export interface PendingRiskExportFilters {
  host_name?: string;
  patch_name?: string;
  baseline_name?: string;
  remediation?: string;
  severity?: string;
  os_type?: string;
}

export interface PendingRiskListParams {
  view: PendingRiskView;
  page: number;
  page_size: number;
  host_id?: number;
  host_name?: string;
  os_type?: string;
  patch_name?: string;
  severity?: string;
  baseline_name?: string;
  remediation?: string;
}

interface CollectPendingRiskExportOptions {
  hostId?: number;
  pageSize?: number;
  maxRows?: number;
}

export function buildPendingRiskListParams(
  view: PendingRiskView,
  filters: PendingRiskExportFilters,
  options: { page: number; pageSize: number; hostId?: number },
): PendingRiskListParams {
  const params: PendingRiskListParams = {
    view,
    page: options.page,
    page_size: options.pageSize,
  };
  if (view === 'host') {
    if (options.hostId) params.host_id = options.hostId;
    if (filters.host_name) params.host_name = filters.host_name;
    if (filters.os_type) params.os_type = filters.os_type === 'win' ? 'windows' : 'linux';
  } else if (view === 'patch') {
    if (filters.patch_name) params.patch_name = filters.patch_name;
    if (filters.severity) params.severity = filters.severity;
  } else if (filters.baseline_name) {
    params.baseline_name = filters.baseline_name;
  }
  if (filters.remediation) params.remediation = filters.remediation;
  return params;
}

export async function collectPendingRiskExportRows<T>(
  getRiskList: (params: PendingRiskListParams) => Promise<{ count?: number; results?: T[] | null }>,
  view: PendingRiskView,
  filters: PendingRiskExportFilters,
  options: CollectPendingRiskExportOptions = {},
): Promise<{ rows: T[]; truncated: boolean; total: number }> {
  const pageSize = options.pageSize ?? PENDING_RISK_EXPORT_PAGE_SIZE;
  const maxRows = options.maxRows ?? PENDING_RISK_EXPORT_MAX_ROWS;
  const rows: T[] = [];
  let page = 1;
  let total = 0;

  while (rows.length < maxRows) {
    const data = await getRiskList(buildPendingRiskListParams(view, filters, {
      page,
      pageSize,
      hostId: options.hostId,
    }));
    const batch = Array.isArray(data?.results) ? data.results : [];
    total = typeof data?.count === 'number' ? data.count : rows.length + batch.length;
    const room = maxRows - rows.length;
    rows.push(...batch.slice(0, room));
    const receivedAll = batch.length === 0 || batch.length < pageSize || rows.length >= total;
    const hitCap = rows.length >= maxRows && total > rows.length;
    if (receivedAll || hitCap) {
      break;
    }
    page += 1;
  }

  return {
    rows,
    truncated: total > rows.length,
    total,
  };
}
