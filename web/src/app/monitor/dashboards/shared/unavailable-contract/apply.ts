import type { GuideItem } from '../types';
import type { MetricUnavailableContract } from './types';
import { buildDashboardQuery } from './build-query';
import { METRIC_UNAVAILABLE_CONTRACTS } from './registry';

const TEMPERATURE_METRIC = 'device_temperature_celsius';

/**
 * 65535°C 不是真实温度。是否排除只看序列标签 collect_type，不看实例名。
 * 华三交换机 / 防火墙插件固定写入 snmp_h3c、snmp_h3c_firewall。
 */
const H3C_TEMPERATURE_COLLECT_TYPES = 'snmp_h3c|snmp_h3c_firewall';
const TEMPERATURE_UINT16_FALLBACK: MetricUnavailableContract = {
  metric: TEMPERATURE_METRIC,
  collectType: '*',
  sentinels: [65535],
  meaning: 'no_sensor',
  displayLabel: '无传感器',
  guideDetail:
    '温度序列上的采集标签 collect_type 为 snmp_h3c 或 snmp_h3c_firewall 时，65535 表示该实体无温度传感器，不计入最高温。实例名不参与判断。其它采集类型的温度原样展示。若显示「--」，表示当前窗口没有温度数据。',
  valueExpr:
    `(device_temperature_celsius{collect_type!~"${H3C_TEMPERATURE_COLLECT_TYPES}", __$labels__} or (device_temperature_celsius{collect_type=~"${H3C_TEMPERATURE_COLLECT_TYPES}", __$labels__} != 65535))`,
  rawExpr:
    `device_temperature_celsius{collect_type=~"${H3C_TEMPERATURE_COLLECT_TYPES}", __$labels__}`,
  aggregate: 'max',
  sentinelPolicy: 'keep_for_display',
  evidence: 'server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_h3c/metrics.json'
};

export const temperatureUint16ByCollectTypeQuery = buildDashboardQuery(TEMPERATURE_UINT16_FALLBACK);

export function findUnavailableContract(
  collectType: string | undefined,
  metric: string
): MetricUnavailableContract | undefined {
  if (!collectType) return undefined;
  return METRIC_UNAVAILABLE_CONTRACTS.find(
    (item) => item.collectType === collectType && item.metric === metric
  );
}

function resolveMetricContract(
  collectType: string | undefined,
  metric: string
): MetricUnavailableContract | undefined {
  const contract = findUnavailableContract(collectType, metric);
  if (metric !== TEMPERATURE_METRIC) return contract;
  // Allied 的无效温度是 128 / -128，不用 65535 规则。
  if (contract?.collectType === 'snmp_alliedtelesis') return contract;
  // 华三最高温只认采集标签，不认实例名。其它品牌温度走同一条查询里的放行分支。
  return TEMPERATURE_UINT16_FALLBACK;
}

export interface MetricContractOverlay {
  name: string;
  query: string;
  unavailableSentinels?: number[];
  unavailableLabel?: string;
}

/** 命中契约时覆盖 query / 哨兵展示字段。华三温度 65535 按 collect_type 排除，不看实例名。 */
export function overlayMetricWithContract<T extends { name: string; query: string; unavailableSentinels?: number[]; unavailableLabel?: string }>(
  metric: T,
  collectType: string | undefined
): T {
  const contract = resolveMetricContract(collectType, metric.name);
  if (!contract) {
    // 拆除静态硬编码残留：未命中契约不得保留哨兵魔法数。
    if (!metric.unavailableSentinels?.length && !metric.unavailableLabel) {
      return metric;
    }
    const rest = { ...metric };
    delete rest.unavailableSentinels;
    delete rest.unavailableLabel;
    return rest;
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

/** 将契约 guideDetail 挂到 KPI / 图例指引；温度未命中品牌时仍附上 65535 说明。 */
export function overlayGuideWithContract(
  guide: GuideItem[] | undefined,
  metric: string,
  collectType: string | undefined,
  fallbackGuide?: GuideItem[]
): GuideItem[] | undefined {
  const contract = resolveMetricContract(collectType, metric);
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
