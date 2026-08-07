import { formatMetricValue } from './format';
import type { BarItem } from '../widgets';

interface RawSeries {
  metric?: Record<string, string>;
  values?: Array<[number, string | number]>;
}

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
      const nums = (s.values || [])
        .filter(([, v]) => v !== null && v !== undefined && v !== '')
        .map(([, v]) => Number(v))
        .filter((n) => Number.isFinite(n));
      const value = nums.length ? nums[nums.length - 1] : 0;
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
