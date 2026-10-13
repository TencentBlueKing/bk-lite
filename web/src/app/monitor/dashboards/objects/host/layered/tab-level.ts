/** 分类页签旁色点。只认 none | warn | critical，警告压提醒。 */

export type TabAlertLevel = 'none' | 'warn' | 'critical';

export type HostCategoryTab = 'overview' | 'system' | 'disk' | 'net' | 'process';

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
}

type ReadingKey = keyof HostTabLevelReadings;

interface ThresholdRule {
  metric: ReadingKey;
  compare: 'above' | 'below';
  warn: number;
  critical: number;
}

/** 高于 warn / critical 达档。后续换表只改这几行。 */
const ABOVE = (metric: ReadingKey, warn: number, critical: number): ThresholdRule => ({
  metric,
  compare: 'above',
  warn,
  critical
});

/** 低于 warn / critical 达档（运行时长：越短越严重）。 */
const BELOW = (metric: ReadingKey, warn: number, critical: number): ThresholdRule => ({
  metric,
  compare: 'below',
  warn,
  critical
});

const CPU = ABOVE('cpu_usage_total', 80, 90);
const MEM = ABOVE('mem_used_percent', 80, 90);
const DISK = ABOVE('disk_used_percent', 80, 90);
const LOAD = ABOVE('system_load1_per_core', 1, 2);
const UPTIME = BELOW('system_uptime', 900, 300);
const SWAP = ABOVE('mem_swap_used_percent', 50, 80);

/** 性能页 iowait：仅当该页把它做成独立 P1 KPI 时才并入。当前瞬时卡没有这张，默认不计入。 */
export const PERF_IOWAIT_RULE = ABOVE('cpu_usage_iowait_total', 20, 40);

export const HOST_TAB_LEVEL_RULES: Record<Exclude<HostCategoryTab, 'process'>, readonly ThresholdRule[]> = {
  overview: [CPU, MEM, DISK, LOAD, UPTIME],
  system: [CPU, MEM, LOAD, UPTIME, SWAP],
  // 磁盘 / 网络首版没有进表的达档指标，保持空表 → 不画点。
  disk: [],
  net: []
};

export interface HostTabLevelOptions {
  includeIowait?: boolean;
}

const RANK: Record<TabAlertLevel, number> = { none: 0, warn: 1, critical: 2 };

const finite = (value: number | null | undefined) => (
  value == null || !Number.isFinite(value) ? null : value
);

export const maxTabLevel = (levels: readonly TabAlertLevel[]): TabAlertLevel => (
  levels.reduce<TabAlertLevel>((best, level) => (RANK[level] > RANK[best] ? level : best), 'none')
);

export const levelAbove = (
  value: number | null | undefined,
  warnAt: number,
  criticalAt: number
): TabAlertLevel => {
  const reading = finite(value);
  if (reading == null) return 'none';
  if (reading >= criticalAt) return 'critical';
  if (reading >= warnAt) return 'warn';
  return 'none';
};

export const levelBelow = (
  value: number | null | undefined,
  warnAt: number,
  criticalAt: number
): TabAlertLevel => {
  const reading = finite(value);
  if (reading == null) return 'none';
  if (reading < criticalAt) return 'critical';
  if (reading < warnAt) return 'warn';
  return 'none';
};

const levelForRule = (rule: ThresholdRule, value: number | null | undefined) => (
  rule.compare === 'below'
    ? levelBelow(value, rule.warn, rule.critical)
    : levelAbove(value, rule.warn, rule.critical)
);

const countLevel = (
  value: number | null | undefined,
  at: number,
  level: Exclude<TabAlertLevel, 'none'>
): TabAlertLevel => {
  const reading = finite(value);
  if (reading == null || reading < at) return 'none';
  return level;
};

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
): TabAlertLevel => {
  if (tab === 'process') {
    return maxTabLevel([
      countLevel(readings.processes_blocked, 1, 'warn'),
      countLevel(readings.processes_zombies, 1, 'critical')
    ]);
  }
  const rules = tab === 'system' && options.includeIowait
    ? [...HOST_TAB_LEVEL_RULES.system, PERF_IOWAIT_RULE]
    : HOST_TAB_LEVEL_RULES[tab];
  return maxTabLevel(rules.map((rule) => levelForRule(rule, readings[rule.metric])));
};
