import type { ChartData } from '@/app/monitor/types';
import type { MetricSeries } from '../../common/simple-dashboard-core';
import type { HostAlertRailEvent } from './events-rail';

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

const DEMO_HOST = 'linux-host-01';

const flagOn = (value: string | null) => {
  const text = (value || '').trim().toLowerCase();
  return text === '1' || text === 'true' || text === 'yes' || text === 'on';
};

const bareInstanceName = (value: string) => value.trim().toLowerCase().split('(')[0].trim();

/**
 * 概览 Events 样例只走演示路径。
 * force：显式 mockEvents / demo 查询，轻轨固定用样例。
 * fill：实例名是 linux-host-01，且接口没有事件时才补样例。
 */
export const hostOverviewEventsDemoMode = (
  names: readonly (string | null | undefined)[],
  search: string
): 'off' | 'fill' | 'force' => {
  const params = new URLSearchParams(search);
  if (flagOn(params.get('mockEvents')) || flagOn(params.get('demo'))) return 'force';
  const candidates = [...names, params.get('instance_name') || ''];
  const named = candidates.some((name) => bareInstanceName(String(name || '')) === DEMO_HOST);
  return named ? 'fill' : 'off';
};

/** 样例时刻按产品默认时区 Asia/Shanghai，轻轨短时间才会显示 12:40 这类钟点。 */
const atShanghaiClock = (hours: number, minutes: number) => {
  const day = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(new Date());
  const hh = String(hours).padStart(2, '0');
  const mm = String(minutes).padStart(2, '0');
  return new Date(`${day}T${hh}:${mm}:00+08:00`).toISOString();
};

/** 演示轻轨样例。不写入告警接口，也不替代真实事件列表。 */
export const hostOverviewDemoEvents = (): HostAlertRailEvent[] => {
  const cpuAt = atShanghaiClock(12, 40);
  const diskAt = atShanghaiClock(11, 2);
  const memAt = atShanghaiClock(10, 18);
  const beatAt = atShanghaiClock(9, 55);
  return [
    {
      id: `demo:cpu:${cpuAt}`,
      alertId: 'demo-cpu',
      at: cpuAt,
      action: 'triggered',
      level: 'critical',
      status: 'closed',
      summary: 'CPU 使用率超过 90%',
      detail: 'CPU 使用率超过 90%'
    },
    {
      id: `demo:disk:${diskAt}`,
      alertId: 'demo-disk',
      at: diskAt,
      action: 'triggered',
      level: 'warning',
      status: 'closed',
      summary: '磁盘 / 使用率 85%',
      detail: '磁盘 / 使用率 85%'
    },
    {
      id: `demo:mem:${memAt}`,
      alertId: 'demo-mem',
      at: memAt,
      action: 'recovered',
      level: 'success',
      status: 'recovered',
      summary: '内存告警已恢复',
      detail: '内存告警已恢复'
    },
    {
      id: `demo:beat:${beatAt}`,
      alertId: 'demo-beat',
      at: beatAt,
      action: 'recovered',
      level: 'info',
      status: 'recovered',
      summary: '主机采集心跳恢复',
      detail: '主机采集心跳恢复'
    }
  ];
};
