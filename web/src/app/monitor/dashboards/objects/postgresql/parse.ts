import { formatMetricValue } from '../../shared/utils';
import type { BarItem } from '../../shared/widgets';

interface RawSeries {
  metric?: Record<string, string>;
  values?: Array<[number, string | number]>;
}

/**
 * 把「按 dbname 聚合 + topk」查询的原始结果(result.data.result 多序列)
 * 解析成按值降序的 BarList items:每序列取最新值、取 dbname label、按值排序。
 * topk 已在查询层限制条数;此处仅排序 + 格式化,数据缺失时返回空数组(空态)。
 */
export const topDbBars = (raw: any, unit: string, color: string): BarItem[] => {
  const series: RawSeries[] = raw?.data?.result || [];
  const rows = series
    .map((s) => {
      const label = s.metric?.dbname || s.metric?.datname || '未知库';
      const nums = (s.values || [])
        .map(([, v]) => Number(v))
        .filter((n) => Number.isFinite(n));
      const value = nums.length ? nums[nums.length - 1] : 0;
      return { label, value };
    })
    .filter((r) => Number.isFinite(r.value))
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
