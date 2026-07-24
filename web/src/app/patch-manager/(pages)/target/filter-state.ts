export interface TargetFilterQuery {
  baselineId?: number;
  complianceStatus?: string;
}

export function parseBaselineFilter(searchParams: URLSearchParams): number | undefined {
  const value = Number(searchParams.get('baseline_id'));
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

export function buildTargetFilterSearch(
  current: URLSearchParams,
  filters: TargetFilterQuery,
): URLSearchParams {
  const next = new URLSearchParams(current.toString());
  if (filters.baselineId) next.set('baseline_id', String(filters.baselineId));
  else next.delete('baseline_id');
  if (filters.complianceStatus) next.set('compliance_status', filters.complianceStatus);
  else next.delete('compliance_status');
  return next;
}
