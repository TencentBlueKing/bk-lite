import { HEALTH_GREEN, HEALTH_AMBER, HEALTH_RED, SATURATION_WARN, SATURATION_CRIT } from './queries';
import { formatMetricValue } from '../../shared/utils';
import { TOP_N } from './queries';

type QueryResult = { data?: { result?: Array<{ metric?: Record<string, string>; values?: Array<[number, string]> }> } } | null;

const lastValue = (values?: Array<[number, string]>): number => {
  if (!values || values.length === 0) return 0;
  const v = Number(values[values.length - 1][1]);
  return Number.isFinite(v) ? v : 0;
};

/** 取单序列结果的最新标量(无数据 → 0)。 */
export const latestScalar = (result: QueryResult): number => {
  const series = result?.data?.result;
  if (!series || series.length === 0) return 0;
  return lastValue(series[0].values);
};

/** 多序列结果 → 按某 label 取每序列最新值(用于 by(phase) / topk(node|pod))。 */
export const seriesLatestByLabel = (result: QueryResult, label: string): Array<{ label: string; value: number }> => {
  const series = result?.data?.result || [];
  return series
    .map((s) => ({ label: String(s.metric?.[label] ?? ''), value: lastValue(s.values) }))
    .filter((item) => item.label !== '');
};

/** by(phase) 结果 → 指定 phase 的计数(无则 0)。 */
export const phaseCount = (result: QueryResult, phase: string): number => {
  const found = seriesLatestByLabel(result, 'phase').find((item) => item.label === phase);
  return found ? found.value : 0;
};

// ── 健康色 ──
export const saturationColor = (maxPct: number): string =>
  maxPct > SATURATION_CRIT ? HEALTH_RED : maxPct > SATURATION_WARN ? HEALTH_AMBER : HEALTH_GREEN;

/** CPU 核数显示(两位小数)。 */
export const coresDisplay = (n: number): string => n.toFixed(2);

/** 字节显示(自动缩写,如 4.3GiB)。 */
export const bytesDisplay = (n: number): string => {
  const f = formatMetricValue(n, 'bytes');
  return `${f.value}${f.unit}`;
};

export interface TopBarItem { label: string; value: number; display: string; color: string; max: number; rank: number }

/** 由 topk 结果按某 label 构建排行 bar items(降序、取前 TOP_N、max 取本卡最大值)。 */
export const buildTopBars = (
  result: Parameters<typeof seriesLatestByLabel>[0],
  label: string,
  color: string,
  format: (n: number) => string
): TopBarItem[] => {
  const rows = seriesLatestByLabel(result, label).sort((a, b) => b.value - a.value).slice(0, TOP_N);
  const max = rows.length ? Math.max(...rows.map((r) => r.value), 1) : 1;
  return rows.map((r, i) => ({ label: r.label, value: r.value, display: format(r.value), color, max, rank: i + 1 }));
};
