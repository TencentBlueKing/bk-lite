import { formatMetricValue } from './format';
import type { BarItem } from '../widgets';

type SeriesPoint = [number, string | number | null | undefined];

interface RawSeries {
  metric?: Record<string, string>;
  values?: SeriesPoint[];
}

/**
 * 取序列最后一个有限值。
 * 后端 fill_missing_points 会把 [最后采样点, end] 之间补成 null；
 * Number(null)===0 且 isFinite(0)，直接取最后一个点会把整列显示成 0。
 */
export const latestFiniteValue = (values?: SeriesPoint[]): number => {
  if (!values?.length) return 0;
  for (let i = values.length - 1; i >= 0; i -= 1) {
    const raw = values[i]?.[1];
    if (raw === null || raw === undefined || raw === '') continue;
    const n = Number(raw);
    if (Number.isFinite(n)) return n;
  }
  return 0;
};

/**
 * 把「按维度 topk」查询结果解析为 BarList。
 * labelKeys 按优先级取第一个非空标签；无标签的序列丢弃，避免把实例级聚合伪装成排行项。
 */
export const topLabelBars = (
  raw: any,
  unit: string,
  color: string,
  labelKeys: string[]
): BarItem[] => {
  const series: RawSeries[] = raw?.data?.result || [];
  const rows = series
    .map((s) => {
      const label = labelKeys.map((k) => (s.metric?.[k] || '').trim()).find(Boolean) || '';
      const value = latestFiniteValue(s.values);
      return { label, value };
    })
    .filter((r) => r.label && Number.isFinite(r.value))
    .sort((a, b) => b.value - a.value);

  const peak = rows.length ? Math.max(...rows.map((r) => r.value)) : 0;
  const max = peak > 0 ? peak : 1;

  return rows.map((r) => {
    const fmt = formatMetricValue(r.value, unit as Parameters<typeof formatMetricValue>[1]);
    return {
      label: r.label,
      value: r.value,
      display: `${fmt.value}${fmt.unit || ''}`,
      color,
      max
    };
  });
};
