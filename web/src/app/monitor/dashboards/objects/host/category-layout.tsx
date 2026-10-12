'use client';

import React, { useEffect, useMemo, useState } from 'react';
import useMonitorApi from '@/app/monitor/api';
import { useFilteredChartPanels } from '../common/dashboard-components';
import { formatDuration, type PreparedChartPanel } from '../common/simple-dashboard-core';
import { formatMetricValue, getLatestChartValue } from '../../shared/utils';
import type { MetricUnit } from '../../shared/types';
import { buildDiskRows, buildLabelRows, seriesHasAnyLabel } from './entity-series';
import type { HostDetailLayoutProps } from './detail-layout';
import type { EntityLoadState } from './use-entity-metrics';
import CategoryNav from './layered/category-nav';
import LayeredEntityStack from './layered/entity-stack';
import FlatProcessSplit from './layered/flat-process-split';
import SignalBar, { type SignalItem } from './layered/signal-bar';
import ThinTimeSeries from './layered/thin-time-series';
import LayeredToolbar from './layered/toolbar';
import styles from './layered/layered.module.scss';

const TOP_CHART_TITLES = ['资源使用趋势', '系统负载趋势'];
const NETWORK_CHART_TITLES = ['网络吞吐趋势', '网络错误速率'];
const DISK_CHART_TITLES = ['磁盘吞吐趋势'];
const DISK_DIMENSIONS = ['path', 'device', 'mount', 'name', 'fstype'];
const EMPTY_ENTITY: EntityLoadState = { status: 'idle', byMetric: {} };
const L1 = {
  teal: '#2dd4bf',
  sky: '#38bdf8',
  amber: '#fbbf24',
  violet: '#a78bfa',
  rose: '#fb7185',
  muted: '#8b98a8'
} as const;

const formatReading = (
  series: { loadState?: string; viewData?: Parameters<typeof getLatestChartValue>[0] } | undefined,
  unit: MetricUnit
) => {
  if (!series || series.loadState !== 'success' || !series.viewData?.length) return '--';
  const latest = getLatestChartValue(series.viewData);
  if (!Number.isFinite(latest)) return '--';
  if (unit === 'none') return String(Number(latest.toFixed(2)));
  if (unit === 's') return formatDuration(latest);
  const formatted = formatMetricValue(latest, unit);
  return `${formatted.value}${formatted.unit || ''}`;
};

const percentTone = (series: { loadState?: string; viewData?: Parameters<typeof getLatestChartValue>[0] } | undefined) => {
  if (!series || series.loadState !== 'success' || !series.viewData?.length) return undefined;
  const latest = getLatestChartValue(series.viewData);
  if (!Number.isFinite(latest)) return undefined;
  if (latest >= 90) return 'var(--l1-crit)';
  if (latest >= 80) return 'var(--l1-warn)';
  return 'var(--l1-ok)';
};

const renderThinChart = (chart: PreparedChartPanel | undefined, loading: boolean) => (
  chart ? (
    <ThinTimeSeries
      title={chart.chart.title}
      data={chart.data}
      legends={chart.legends.map((item) => ({ label: item.label, color: item.color }))}
      unit={chart.unit}
      loading={loading}
    />
  ) : null
);

/** L1 密度工作台：仅 host_layout=category。禁止复用 KpiSection / 白卡 / 重面积图。 */
export default function HostCategoryLayout({
  dashboard,
  diskState,
  netState,
  gpuState,
  processReady,
  processState = EMPTY_ENTITY,
  layout = 'category',
  onLayoutChange,
  categoryTab = 'system',
  onCategoryTabChange
}: HostDetailLayoutProps) {
  const { getMonitorAlert } = useMonitorApi();
  const [uncontrolledTab, setUncontrolledTab] = useState('system');
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const activeTab = onCategoryTabChange ? categoryTab : uncontrolledTab;
  const setActiveTab = onCategoryTabChange || setUncontrolledTab;
  const metrics = dashboard.metricSeries;
  const topCharts = useFilteredChartPanels(dashboard.chartPanels, TOP_CHART_TITLES);
  const networkCharts = useFilteredChartPanels(dashboard.chartPanels, NETWORK_CHART_TITLES);
  const diskCharts = useFilteredChartPanels(dashboard.chartPanels, DISK_CHART_TITLES);
  const [resourceChart, loadChart] = topCharts;
  const [networkChart, networkErrorChart] = networkCharts;
  const [diskChart] = diskCharts;

  const diskSeries = useMemo(() => Object.values(diskState.byMetric).flat(), [diskState.byMetric]);
  const netSeries = useMemo(() => Object.values(netState.byMetric).flat(), [netState.byMetric]);
  const gpuSeries = useMemo(() => Object.values(gpuState.byMetric).flat(), [gpuState.byMetric]);
  const diskRows = useMemo(() => buildDiskRows(diskState.byMetric), [diskState.byMetric]);
  const netRows = useMemo(
    () => buildLabelRows(netState.byMetric, 'interface', 'net_bytes_recv_rate'),
    [netState.byMetric]
  );
  const gpuRows = useMemo(
    () => buildLabelRows(gpuState.byMetric, 'index', 'nvidia_smi_utilization_memory'),
    [gpuState.byMetric]
  );
  const processRows = useMemo(
    () => buildLabelRows(processState.byMetric, 'process_name', 'process_cpu_usage'),
    [processState.byMetric]
  );
  const diskHasDimension = seriesHasAnyLabel(diskSeries, DISK_DIMENSIONS);
  const netHasInterface = seriesHasAnyLabel(netSeries, ['interface']);
  const gpuHasIndex = seriesHasAnyLabel(gpuSeries, ['index']);
  const diskLoading = diskState.status === 'idle' || diskState.status === 'loading';
  const netLoading = netState.status === 'idle' || netState.status === 'loading';
  const gpuLoading = gpuState.status === 'idle' || gpuState.status === 'loading';
  const processLoading = processState.status === 'idle' || processState.status === 'loading';
  const showGpu = gpuState.status !== 'empty';

  useEffect(() => {
    if (activeTab === 'process' && !processReady) setActiveTab('system');
    if (activeTab === 'gpu' && gpuState.status === 'empty') setActiveTab('system');
  }, [activeTab, gpuState.status, processReady, setActiveTab]);

  useEffect(() => {
    const instanceId = String(dashboard.instanceId || '');
    if (!instanceId) {
      setAlertCount(null);
      return;
    }
    let active = true;
    getMonitorAlert({
      monitor_instance_id: instanceId,
      status_in: 'new' as unknown as string[],
      page: 1,
      page_size: 1
    })
      .then((data) => {
        if (active) setAlertCount(typeof data?.count === 'number' ? data.count : 0);
      })
      .catch(() => {
        if (active) setAlertCount(null);
      });
    return () => {
      active = false;
    };
  }, [dashboard.instanceId, getMonitorAlert]);

  const signalItems = useMemo<SignalItem[]>(() => {
    const cpu = metrics.cpu_usage_total;
    const mem = metrics.mem_used_percent;
    const disk = metrics.disk_used_percent;
    const load = metrics.system_load1;
    const netIn = metrics.net_bytes_recv_rate;
    const items: SignalItem[] = [
      {
        key: 'cpu',
        label: 'CPU',
        value: formatReading(cpu, 'percent'),
        color: L1.teal,
        tone: percentTone(cpu),
        trend: cpu?.viewData || []
      },
      {
        key: 'mem',
        label: '内存',
        value: formatReading(mem, 'percent'),
        color: L1.sky,
        tone: percentTone(mem),
        trend: mem?.viewData || []
      },
      {
        key: 'disk',
        label: '磁盘',
        value: formatReading(disk, 'percent'),
        color: L1.amber,
        tone: percentTone(disk),
        trend: disk?.viewData || []
      }
    ];
    if (load?.loadState === 'success' && load.viewData?.length) {
      items.push({
        key: 'load',
        label: 'Load',
        value: formatReading(load, 'none'),
        color: L1.violet,
        trend: load.viewData
      });
    }
    items.push({
      key: 'net',
      label: '网络入',
      value: formatReading(netIn, 'byteps'),
      color: L1.rose,
      trend: netIn?.viewData || []
    });
    return items;
  }, [metrics]);

  const navItems = [
    { key: 'system', label: '系统' },
    { key: 'disk', label: '磁盘', count: diskState.status === 'ready' ? diskRows.length : undefined },
    { key: 'net', label: '网络', count: netState.status === 'ready' ? netRows.length : undefined },
    ...(processReady
      ? [{ key: 'process', label: '进程', count: processState.status === 'ready' ? processRows.length : undefined }]
      : []),
    ...(showGpu
      ? [{ key: 'gpu', label: 'GPU', count: gpuState.status === 'ready' ? gpuRows.length : undefined }]
      : [])
  ];

  const statusRows = [
    { key: 'uptime', label: '运行时长', value: formatReading(metrics.system_uptime, 's') },
    { key: 'blocked', label: '阻塞进程', value: formatReading(metrics.processes_blocked, 'counts') },
    { key: 'zombies', label: '僵尸进程', value: formatReading(metrics.processes_zombies, 'counts') }
  ].filter((row) => row.value !== '--' || row.key === 'uptime');

  const renderPane = () => {
    if (activeTab === 'disk') {
      if (diskState.status === 'error') {
        return <div className={styles.note}>磁盘维度查询失败，请稍后重试。</div>;
      }
      if (diskHasDimension || diskLoading) {
        return (
          <LayeredEntityStack
            loading={diskLoading}
            rows={diskRows}
            columns={[
              { key: 'path', title: 'path', labelKey: 'path' },
              { key: 'device', title: 'device', labelKey: 'device' },
              { key: 'disk_used_percent', title: 'used%', unit: 'percent' },
              { key: 'disk_inodes_used_percent', title: 'inodes%', unit: 'percent' },
              { key: 'diskio_io_util', title: 'IO util', unit: 'percent' },
              { key: 'diskio_read_bytes_rate', title: '读字节率', unit: 'byteps' },
              { key: 'diskio_write_bytes_rate', title: '写字节率', unit: 'byteps' }
            ]}
            chartMetrics={[
              { key: 'disk_used_percent', label: 'used%', unit: 'percent', color: L1.amber },
              { key: 'disk_inodes_used_percent', label: 'inodes%', unit: 'percent', color: L1.muted },
              { key: 'diskio_io_util', label: 'IO util', unit: 'percent', color: L1.rose },
              { key: 'diskio_read_bytes_rate', label: '读', unit: 'byteps', color: L1.teal },
              { key: 'diskio_write_bytes_rate', label: '写', unit: 'byteps', color: L1.sky }
            ]}
          />
        );
      }
      return (
        <>
          <div className={styles.note}>当前磁盘序列没有 path/device 维度，仅保留主机合计吞吐。</div>
          {renderThinChart(diskChart, dashboard.loading)}
        </>
      );
    }
    if (activeTab === 'net') {
      if (netState.status === 'error') {
        return <div className={styles.note}>网卡维度查询失败，请稍后重试。</div>;
      }
      if (netHasInterface || netLoading) {
        return (
          <LayeredEntityStack
            loading={netLoading}
            rows={netRows}
            columns={[
              { key: 'interface', title: 'interface', labelKey: 'interface' },
              { key: 'net_bytes_recv_rate', title: 'bytes in', unit: 'byteps' },
              { key: 'net_bytes_sent_rate', title: 'bytes out', unit: 'byteps' },
              { key: 'net_err_in_rate', title: 'err in', unit: 'cps' },
              { key: 'net_err_out_rate', title: 'err out', unit: 'cps' },
              { key: 'net_drop_in_rate', title: 'drop in', unit: 'cps' },
              { key: 'net_drop_out_rate', title: 'drop out', unit: 'cps' }
            ]}
            chartMetrics={[
              { key: 'net_bytes_recv_rate', label: 'bytes in', unit: 'byteps', color: L1.teal },
              { key: 'net_bytes_sent_rate', label: 'bytes out', unit: 'byteps', color: L1.sky },
              { key: 'net_err_in_rate', label: 'err in', unit: 'cps', color: L1.amber },
              { key: 'net_err_out_rate', label: 'err out', unit: 'cps', color: L1.rose },
              { key: 'net_drop_in_rate', label: 'drop in', unit: 'cps', color: L1.violet },
              { key: 'net_drop_out_rate', label: 'drop out', unit: 'cps', color: L1.muted }
            ]}
          />
        );
      }
      return (
        <>
          <div className={styles.note}>当前网络序列没有 interface 维度。下面是全接口合计。</div>
          <div className={styles.chartGrid}>
            {renderThinChart(networkChart, dashboard.loading)}
            {renderThinChart(networkErrorChart, dashboard.loading)}
          </div>
        </>
      );
    }
    if (activeTab === 'process') {
      return <FlatProcessSplit rows={processRows} loading={processLoading} />;
    }
    if (activeTab === 'gpu') {
      if (gpuHasIndex || gpuLoading) {
        return (
          <LayeredEntityStack
            loading={gpuLoading}
            rows={gpuRows}
            columns={[
              { key: 'index', title: 'index', labelKey: 'index' },
              { key: 'nvidia_smi_utilization_memory', title: '显存%', unit: 'percent' },
              { key: 'nvidia_smi_temperature_gpu', title: '温度', unit: 'celsius' },
              { key: 'nvidia_smi_power_draw', title: '功耗', unit: 'watts' },
              { key: 'nvidia_smi_fan_speed_avg', title: '风扇%', unit: 'percent' }
            ]}
            chartMetrics={[
              { key: 'nvidia_smi_utilization_memory', label: '显存%', unit: 'percent', color: L1.teal },
              { key: 'nvidia_smi_temperature_gpu', label: '温度', unit: 'celsius', color: L1.rose },
              { key: 'nvidia_smi_power_draw', label: '功耗', unit: 'watts', color: L1.amber },
              { key: 'nvidia_smi_fan_speed_avg', label: '风扇%', unit: 'percent', color: L1.sky }
            ]}
          />
        );
      }
      return <div className={styles.note}>已采到 GPU 序列，但没有 index 维度，因此不展开单卡表。</div>;
    }
    return (
      <>
        <div className={styles.chartGrid}>
          {renderThinChart(resourceChart, dashboard.loading)}
          {renderThinChart(loadChart, dashboard.loading)}
        </div>
        <table className={styles.statusTable}>
          <tbody>
            {statusRows.map((row) => (
              <tr key={row.key}>
                <td>{row.label}</td>
                <td>{row.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    );
  };

  return (
    <div className={styles.root}>
      <LayeredToolbar
        dashboard={dashboard}
        layout={layout}
        onLayoutChange={onLayoutChange || (() => undefined)}
      />
      <SignalBar items={signalItems} alertCount={alertCount} />
      <div className={styles.body}>
        <CategoryNav items={navItems} activeKey={activeTab} onChange={setActiveTab} />
        <div className={styles.main}>
          <div className={styles.paneTitle}>
            {navItems.find((item) => item.key === activeTab)?.label || '系统'}
          </div>
          {renderPane()}
        </div>
      </div>
    </div>
  );
}
