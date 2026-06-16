import { formatMetricValue } from '../../shared/utils';
import type { BarItem } from '../../shared/widgets';

interface RawSeries {
  metric?: Record<string, string>;
  values?: Array<[number, string | number]>;
}

/**
 * 把「按 db 聚合 + topk」查询的原始结果(result.data.result 多序列)
 * 解析成按值降序的 BarList items:每序列取最新值、取 db label、按值排序。
 * topk 已在查询层限制条数;此处仅排序 + 格式化,数据缺失时返回空数组(空态)。
 */
export const topDbBars = (raw: any, unit: string, color: string): BarItem[] => {
  const series: RawSeries[] = raw?.data?.result || [];
  const rows = series
    .map((s) => {
      // 仅用真实的 db/datname 标签;缺失或空串说明该数据没有按库维度,
      // 不再伪造「未知库」(否则会把实例级聚合值误展示成某个库的排行)。
      const label = (s.metric?.db || s.metric?.datname || '').trim();
      // 后端 fill_missing_points 会把 [最后采样点, end] 之间补成 null;因 Number(null)===0,
      // 必须先剔除这些占位点,否则「取最后一个点」会拿到补出来的 0,导致整列显示 0。
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
