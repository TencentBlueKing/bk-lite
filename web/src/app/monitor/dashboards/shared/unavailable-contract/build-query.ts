import type { MetricUnavailableContract } from './types';

/** 按契约生成仪表盘聚合 PromQL（含 __$labels__）。 */
export function buildDashboardQuery(contract: MetricUnavailableContract): string {
  const agg = contract.aggregate;
  const filtered = `${agg}(${contract.valueExpr}) by (instance_id)`;
  if (contract.sentinelPolicy !== 'keep_for_display') {
    return filtered;
  }
  if (!contract.rawExpr) {
    throw new Error(
      `keep_for_display contract ${contract.collectType}/${contract.metric} requires rawExpr`
    );
  }
  return `${filtered} or ${agg}(${contract.rawExpr}) by (instance_id)`;
}

/** 导出全部契约构造的模板，供 dashboard_query_capabilities 清单收录。 */
export function listContractDashboardQueries(
  contracts: readonly MetricUnavailableContract[]
): string[] {
  return contracts.map((contract) => buildDashboardQuery(contract));
}
