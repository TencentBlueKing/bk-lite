import type { ChartData } from '@/app/monitor/types';
import type { MetricSeries } from '../../common/simple-dashboard-core';

const GiB = 1024 ** 3;

const stubSeries = (
  name: string,
  value: number,
  unit: MetricSeries['unit']
): MetricSeries => ({
  name,
  display_name: name,
  description: name,
  unit,
  query: '',
  color: '#94A3B8',
  loadState: 'success',
  viewData: [{ time: Date.now(), value1: value }]
});

const patchLatest = (
  series: MetricSeries | undefined,
  name: string,
  value: number,
  unit: MetricSeries['unit']
): MetricSeries => {
  if (!series?.viewData?.length) return stubSeries(name, value, unit);
  const viewData = series.viewData.map((point, index, list) => (
    index === list.length - 1
      ? { ...point, value1: value } as ChartData
      : point
  ));
  return { ...series, loadState: 'success', viewData };
};

/** 演示达档：概览提醒（CPU 85）、性能警告（交换 85%）、进程警告（僵尸 ≥1）。 */
export const applyHostTabDemoSeries = (
  series: Record<string, MetricSeries | undefined>
): Record<string, MetricSeries | undefined> => {
  const next = { ...series };
  const set = (name: string, value: number, unit: MetricSeries['unit']) => {
    next[name] = patchLatest(next[name], name, value, unit);
  };
  set('cpu_usage_total', 85, 'percent');
  set('mem_used_percent', 72, 'percent');
  set('disk_used_percent', 48, 'percent');
  set('cpu_n', 8, 'counts');
  set('system_load1', 4, 'none');
  set('host_mem_swap_used_bytes', 6.8 * GiB, 'bytes');
  set('host_mem_swap_total_bytes', 8 * GiB, 'bytes');
  set('mem_swap_free', 1.2 * GiB, 'bytes');
  set('processes_zombies', 1, 'counts');
  set('processes_blocked', 0, 'counts');
  if (!next.system_uptime?.viewData?.length) {
    set('system_uptime', 86400 * 18, 's');
  }
  return next;
};
