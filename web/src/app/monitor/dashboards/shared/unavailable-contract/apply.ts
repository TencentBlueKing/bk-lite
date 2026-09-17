import type { GuideItem } from '../types';
import type { MetricUnavailableContract } from './types';
import { buildDashboardQuery } from './build-query';
import { METRIC_UNAVAILABLE_CONTRACTS } from './registry';

export function findUnavailableContract(
  collectType: string | undefined,
  metric: string
): MetricUnavailableContract | undefined {
  if (!collectType) return undefined;
  return METRIC_UNAVAILABLE_CONTRACTS.find(
    (item) => item.collectType === collectType && item.metric === metric
  );
}

export interface MetricContractOverlay {
  name: string;
  query: string;
  unavailableSentinels?: number[];
  unavailableLabel?: string;
}

/** 命中契约时覆盖 query / 哨兵展示字段；未命中原样返回。 */
export function overlayMetricWithContract<T extends { name: string; query: string; unavailableSentinels?: number[]; unavailableLabel?: string }>(
  metric: T,
  collectType: string | undefined
): T {
  const contract = findUnavailableContract(collectType, metric.name);
  if (!contract) {
    // 拆除静态硬编码残留：未命中契约不得保留哨兵魔法数。
    if (metric.unavailableSentinels?.length || metric.unavailableLabel) {
      const { unavailableSentinels: _s, unavailableLabel: _l, ...rest } = metric;
      return rest as T;
    }
    return metric;
  }
  return {
    ...metric,
    query: buildDashboardQuery(contract),
    unavailableSentinels:
      contract.sentinelPolicy === 'keep_for_display' && contract.sentinels.length
        ? [...contract.sentinels]
        : undefined,
    unavailableLabel:
      contract.sentinelPolicy === 'keep_for_display' ? contract.displayLabel : undefined
  };
}

export function overlayMetricsWithContracts<T extends { name: string; query: string; unavailableSentinels?: number[]; unavailableLabel?: string }>(
  metrics: T[],
  collectType: string | undefined
): T[] {
  return metrics.map((metric) => overlayMetricWithContract(metric, collectType));
}

/** 将契约 guideDetail 挂到 KPI / 图例指引；无契约时保留原 guide。 */
export function overlayGuideWithContract(
  guide: GuideItem[] | undefined,
  metric: string,
  collectType: string | undefined,
  fallbackGuide?: GuideItem[]
): GuideItem[] | undefined {
  const contract = findUnavailableContract(collectType, metric);
  if (!contract?.guideDetail) {
    return guide ?? fallbackGuide;
  }
  const base = (guide && guide.length ? guide : fallbackGuide) || [];
  const primary = base[0];
  const sentinelItem: GuideItem = {
    label: contract.displayLabel,
    detail: contract.guideDetail
  };
  if (!primary) return [sentinelItem];
  // 保留首条指标说明，替换/追加哨兵说明（去掉旧的硬编码哨兵条）。
  const rest = base.slice(1).filter((item) => item.label !== contract.displayLabel);
  return [primary, sentinelItem, ...rest];
}
