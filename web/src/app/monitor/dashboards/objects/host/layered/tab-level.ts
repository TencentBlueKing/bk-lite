/** 分类页签旁色点。只认 none | warn | critical，警告压提醒。 */

export type TabAlertLevel = 'none' | 'warn' | 'critical';

export type HostCategoryTab = 'overview' | 'system' | 'disk' | 'net' | 'process';

export type ThresholdOp = '>=' | '<';

export interface HostTabLevelReadings {
  cpu_usage_total?: number | null;
  mem_used_percent?: number | null;
  disk_used_percent?: number | null;
  system_load1_per_core?: number | null;
  system_uptime?: number | null;
  mem_swap_used_percent?: number | null;
  cpu_usage_iowait_total?: number | null;
  processes_blocked?: number | null;
  processes_zombies?: number | null;
  process_cpu_usage?: number | null;
  process_mem_usage?: number | null;
}

export interface HostMetricThreshold {
  metric_key: keyof HostTabLevelReadings;
  pages: readonly HostCategoryTab[];
  warn_op?: ThresholdOp;
  warn_value?: number;
  crit_op?: ThresholdOp;
  crit_value?: number;
}

/**
 * 主机分类页签达档表。同页 max(level)；无达档不画点。
 * iowait 首版不挂页；includeIowait 时才并入性能页。
 */
export const HOST_METRIC_THRESHOLDS: readonly HostMetricThreshold[] = [
  { metric_key: 'cpu_usage_total', pages: ['overview', 'system'], warn_op: '>=', warn_value: 80, crit_op: '>=', crit_value: 90 },
  { metric_key: 'mem_used_percent', pages: ['overview', 'system'], warn_op: '>=', warn_value: 80, crit_op: '>=', crit_value: 90 },
  { metric_key: 'disk_used_percent', pages: ['overview'], warn_op: '>=', warn_value: 80, crit_op: '>=', crit_value: 90 },
  { metric_key: 'system_load1_per_core', pages: ['overview', 'system'], warn_op: '>=', warn_value: 1, crit_op: '>=', crit_value: 2 },
  { metric_key: 'mem_swap_used_percent', pages: ['system'], warn_op: '>=', warn_value: 50, crit_op: '>=', crit_value: 80 },
  { metric_key: 'cpu_usage_iowait_total', pages: [], warn_op: '>=', warn_value: 20, crit_op: '>=', crit_value: 40 },
  { metric_key: 'system_uptime', pages: ['overview', 'system'], warn_op: '<', warn_value: 900, crit_op: '<', crit_value: 300 },
  { metric_key: 'processes_blocked', pages: ['process'], warn_op: '>=', warn_value: 1 },
  { metric_key: 'processes_zombies', pages: ['process'], crit_op: '>=', crit_value: 1 },
  { metric_key: 'process_cpu_usage', pages: ['process'], warn_op: '>=', warn_value: 70, crit_op: '>=', crit_value: 90 },
  { metric_key: 'process_mem_usage', pages: ['process'], warn_op: '>=', warn_value: 40, crit_op: '>=', crit_value: 80 }
];

export interface HostTabLevelOptions {
  includeIowait?: boolean;
}

const RANK: Record<TabAlertLevel, number> = { none: 0, warn: 1, critical: 2 };

const finite = (value: number | null | undefined) => (
  value == null || !Number.isFinite(value) ? null : value
);

const matchOp = (value: number, op: ThresholdOp, bound: number) => (
  op === '<' ? value < bound : value >= bound
);

export const maxTabLevel = (levels: readonly TabAlertLevel[]): TabAlertLevel => (
  levels.reduce<TabAlertLevel>((best, level) => (RANK[level] > RANK[best] ? level : best), 'none')
);

export const evaluateMetricLevel = (
  rule: HostMetricThreshold,
  value: number | null | undefined
): TabAlertLevel => {
  const reading = finite(value);
  if (reading == null) return 'none';
  if (rule.crit_op != null && rule.crit_value != null && matchOp(reading, rule.crit_op, rule.crit_value)) {
    return 'critical';
  }
  if (rule.warn_op != null && rule.warn_value != null && matchOp(reading, rule.warn_op, rule.warn_value)) {
    return 'warn';
  }
  return 'none';
};

const rulesForTab = (tab: HostCategoryTab, options: HostTabLevelOptions) => (
  HOST_METRIC_THRESHOLDS.filter((rule) => {
    if (rule.metric_key === 'cpu_usage_iowait_total') {
      return Boolean(options.includeIowait) && tab === 'system';
    }
    return rule.pages.includes(tab);
  })
);

/** load1 / 核数。缺核或核数非正时不造读数。 */
export const loadPerCore = (load: number | null | undefined, cores: number | null | undefined) => {
  const loadValue = finite(load);
  const coreValue = finite(cores);
  if (loadValue == null || coreValue == null || coreValue <= 0) return null;
  return loadValue / coreValue;
};

/** 交换已用占比。优先已用/总量，没有已用字节时用总量减空闲。 */
export const swapUsedPercent = (
  used: number | null | undefined,
  total: number | null | undefined,
  free: number | null | undefined
) => {
  const totalValue = finite(total);
  if (totalValue == null || totalValue <= 0) return null;
  const usedValue = finite(used);
  const freeValue = finite(free);
  const raw = usedValue != null
    ? (100 * usedValue) / totalValue
    : freeValue != null
      ? (100 * (totalValue - freeValue)) / totalValue
      : null;
  if (raw == null) return null;
  return Math.min(100, Math.max(0, raw));
};

export const resolveHostTabLevel = (
  tab: HostCategoryTab,
  readings: HostTabLevelReadings,
  options: HostTabLevelOptions = {}
): TabAlertLevel => (
  maxTabLevel(rulesForTab(tab, options).map((rule) => evaluateMetricLevel(rule, readings[rule.metric_key])))
);

/** 同一页、同一批读数里，若干指标的最高达档。指标不在该页则不计入。 */
export const resolveMetricLevels = (
  tab: HostCategoryTab,
  readings: HostTabLevelReadings,
  keys: readonly (keyof HostTabLevelReadings)[],
  options: HostTabLevelOptions = {}
): TabAlertLevel => (
  maxTabLevel(
    rulesForTab(tab, options)
      .filter((rule) => keys.includes(rule.metric_key))
      .map((rule) => evaluateMetricLevel(rule, readings[rule.metric_key]))
  )
);

export interface HostSurfaceAlerts {
  overview: {
    cpu: TabAlertLevel;
    mem: TabAlertLevel;
    disk: TabAlertLevel;
    load: TabAlertLevel;
    uptime: TabAlertLevel;
  };
  system: {
    cpu: TabAlertLevel;
    mem: TabAlertLevel;
    load: TabAlertLevel;
    uptime: TabAlertLevel;
  };
  process: {
    blocked: TabAlertLevel;
    zombies: TabAlertLevel;
    list: TabAlertLevel;
  };
}

/**
 * 卡气味与页签点同源。每张卡只吃自己展示的指标。
 * 同一指标的趋势图不再打点，读数卡优先。
 * 交换达档仍只点亮性能页签。详细区交换图是趋势，不另打折角。
 */
export const resolveHostSurfaceAlerts = (
  readings: HostTabLevelReadings,
  options: HostTabLevelOptions = {}
): HostSurfaceAlerts => ({
  overview: {
    cpu: resolveMetricLevels('overview', readings, ['cpu_usage_total'], options),
    mem: resolveMetricLevels('overview', readings, ['mem_used_percent'], options),
    disk: resolveMetricLevels('overview', readings, ['disk_used_percent'], options),
    load: resolveMetricLevels('overview', readings, ['system_load1_per_core'], options),
    uptime: resolveMetricLevels('overview', readings, ['system_uptime'], options)
  },
  system: {
    cpu: resolveMetricLevels('system', readings, ['cpu_usage_total'], options),
    mem: resolveMetricLevels('system', readings, ['mem_used_percent'], options),
    load: resolveMetricLevels('system', readings, ['system_load1_per_core'], options),
    uptime: resolveMetricLevels('system', readings, ['system_uptime'], options)
  },
  process: {
    blocked: resolveMetricLevels('process', readings, ['processes_blocked'], options),
    zombies: resolveMetricLevels('process', readings, ['processes_zombies'], options),
    list: resolveMetricLevels('process', readings, ['process_cpu_usage', 'process_mem_usage'], options)
  }
});
