'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Tabs } from 'antd';
import { useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import MetricViews from '@/app/monitor/components/metric-views';
import {
  DashboardSectionLabel,
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredRingPanels
} from '../common/dashboard-components';
import type { PreparedChartPanel } from '../common/simple-dashboard-core';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import { RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { HOST_DASHBOARD_CONFIG, HOST_PALETTE } from './config';
import {
  HOST_DISK_ENTITY_QUERIES,
  HOST_GPU_ENTITY_QUERIES,
  HOST_NET_ENTITY_QUERIES
} from './queries';
import {
  buildDiskRows,
  buildLabelRows,
  seriesHasAnyLabel
} from './entity-series';
import HostEntityLayer from './entity-layer';
import { useHostEntityMetrics } from './use-entity-metrics';
import { HOST_PROCESS_METRICS_TAB, resolveHostProcessMetricsTarget } from './host-process-metrics-tab';
import styles from './index.module.scss';

const TOP_CHART_TITLES = ['资源使用趋势', '系统负载趋势'];
const NETWORK_CHART_TITLES = ['网络吞吐趋势', '网络错误速率'];
const DISK_CHART_TITLES = ['磁盘吞吐趋势'];
const RING_TITLES = ['CPU 时间分布'];
const PROCESS_ANOMALY_TITLES = ['进程异常趋势'];

const DISK_DIMENSIONS = ['path', 'device', 'mount', 'name', 'fstype'];

export default function HostDashboardPage() {
  const dashboard = useSimpleDashboardData(HOST_DASHBOARD_CONFIG);
  const monitorApi = useMonitorApi();
  const apiRef = useRef(monitorApi);
  apiRef.current = monitorApi;
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams]
  );
  const [activeTab, setActiveTab] = useState('system');
  const [processReady, setProcessReady] = useState(false);

  const topCharts = useFilteredChartPanels(dashboard.chartPanels, TOP_CHART_TITLES);
  const networkCharts = useFilteredChartPanels(dashboard.chartPanels, NETWORK_CHART_TITLES);
  const diskCharts = useFilteredChartPanels(dashboard.chartPanels, DISK_CHART_TITLES);
  const anomalyCharts = useFilteredChartPanels(dashboard.chartPanels, PROCESS_ANOMALY_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const [resourceChart, loadChart] = topCharts;
  const [networkChart, networkErrorChart] = networkCharts;
  const [diskChart] = diskCharts;
  const [processAnomalyChart] = anomalyCharts;
  const [cpuRing] = rings;

  const {
    idValues,
    timeValues,
    isDashboardMode,
    loadTick,
    currentInstanceInterval,
    monitorObjectId,
    instanceId
  } = dashboard;

  const entityArgs = {
    idValues,
    instanceIdKeys,
    timeValues,
    monitorObjectId,
    instanceId,
    minStepSeconds: currentInstanceInterval,
    loadTick,
    isDashboardMode
  };
  const diskState = useHostEntityMetrics({ ...entityArgs, enabled: true, queries: HOST_DISK_ENTITY_QUERIES });
  const netState = useHostEntityMetrics({ ...entityArgs, enabled: true, queries: HOST_NET_ENTITY_QUERIES });
  const gpuState = useHostEntityMetrics({ ...entityArgs, enabled: true, queries: HOST_GPU_ENTITY_QUERIES });

  useEffect(() => {
    let active = true;
    resolveHostProcessMetricsTarget({
      getMonitorObject: (params) => apiRef.current.getMonitorObject(params),
      getMonitorPlugin: (params) => apiRef.current.getMonitorPlugin(params)
    }).then((target) => {
      if (active) setProcessReady(Boolean(target));
    });
    return () => {
      active = false;
    };
  }, [monitorObjectId]);

  const diskSeries = useMemo(
    () => Object.values(diskState.byMetric).flat(),
    [diskState.byMetric]
  );
  const netSeries = useMemo(
    () => Object.values(netState.byMetric).flat(),
    [netState.byMetric]
  );
  const gpuSeries = useMemo(
    () => Object.values(gpuState.byMetric).flat(),
    [gpuState.byMetric]
  );
  const diskRows = useMemo(() => buildDiskRows(diskState.byMetric), [diskState.byMetric]);
  const netRows = useMemo(
    () => buildLabelRows(netState.byMetric, 'interface', 'net_bytes_recv_rate'),
    [netState.byMetric]
  );
  const gpuRows = useMemo(
    () => buildLabelRows(gpuState.byMetric, 'index', 'nvidia_smi_utilization_memory'),
    [gpuState.byMetric]
  );
  const diskHasDimension = seriesHasAnyLabel(diskSeries, DISK_DIMENSIONS);
  const netHasInterface = seriesHasAnyLabel(netSeries, ['interface']);
  const gpuHasIndex = seriesHasAnyLabel(gpuSeries, ['index']);
  const showDisk = diskState.status === 'error' || (diskState.status === 'ready' && (diskHasDimension || diskSeries.length > 0));
  const showNet = netState.status === 'error' || (netState.status === 'ready' && netSeries.length > 0);
  const showGpu = gpuState.status === 'ready' && gpuSeries.length > 0;

  useEffect(() => {
    const visible = new Set(['system']);
    if (showDisk) visible.add('disk');
    if (showNet) visible.add('net');
    if (processReady) visible.add('process');
    if (showGpu) visible.add('gpu');
    if (!visible.has(activeTab)) setActiveTab('system');
  }, [activeTab, processReady, showDisk, showGpu, showNet]);

  const renderTrend = (chart: PreparedChartPanel | undefined, className: string) => chart ? (
    <TrendChartPanel
      key={chart.chart.title}
      title={chart.chart.title}
      subtitle={chart.chart.subtitle}
      guide={chart.chart.guide}
      legends={chart.legends}
      data={chart.data}
      metric={chart.metric}
      unit={chart.unit}
      loading={dashboard.loading}
      seriesStyles={chart.seriesStyles}
      onXRangeChange={dashboard.onXRangeChange}
      className={className}
      styles={styles}
    />
  ) : null;

  const tabItems: Array<{ key: string; label: string; children: React.ReactNode }> = [
    {
      key: 'system',
      label: '系统',
      children: (
        <>
          <DashboardSectionLabel styles={styles}>性能与分布</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            {renderTrend(resourceChart, `${styles.span4} ${styles.compactTrend}`)}
            {renderTrend(loadChart, `${styles.span4} ${styles.compactTrend}`)}
            {cpuRing ? (
              <RingChartPanel
                key={cpuRing.panel.title}
                title={cpuRing.panel.title}
                subtitle={cpuRing.panel.subtitle}
                guide={cpuRing.panel.guide}
                data={cpuRing.data}
                centerValue={cpuRing.centerValue}
                centerCaption={cpuRing.panel.centerCaption}
                isEmpty={cpuRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {renderTrend(processAnomalyChart, `${styles.span4} ${styles.compactTrend}`)}
          </FlexiblePanelSection>
        </>
      )
    }
  ];

  if (showDisk) {
    tabItems.push({
      key: 'disk',
      label: '磁盘',
      children: diskState.status === 'error' ? (
        <div className={styles.layerNote}>磁盘维度查询失败，请稍后重试。</div>
      ) : diskHasDimension ? (
        <HostEntityLayer
          styles={styles}
          loading={diskState.status === 'loading'}
          rows={diskRows}
          onXRangeChange={dashboard.onXRangeChange}
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
            { key: 'disk_used_percent', label: 'used%', unit: 'percent', color: HOST_PALETTE.amber },
            { key: 'disk_inodes_used_percent', label: 'inodes%', unit: 'percent', color: HOST_PALETTE.neutral },
            { key: 'diskio_io_util', label: 'IO util', unit: 'percent', color: HOST_PALETTE.orange },
            { key: 'diskio_read_bytes_rate', label: '读', unit: 'byteps', color: HOST_PALETTE.cyan },
            { key: 'diskio_write_bytes_rate', label: '写', unit: 'byteps', color: HOST_PALETTE.rose }
          ]}
        />
      ) : (
        <>
          <div className={styles.layerNote}>当前磁盘序列没有 path/device 维度，仅保留主机合计吞吐，不把合计画成挂载点明细。</div>
          <FlexiblePanelSection styles={styles}>
            {renderTrend(diskChart, `${styles.span6} ${styles.compactTrend}`)}
          </FlexiblePanelSection>
        </>
      )
    });
  }

  if (showNet) {
    tabItems.push({
      key: 'net',
      label: '网络',
      children: netState.status === 'error' ? (
        <div className={styles.layerNote}>网卡维度查询失败，请稍后重试。</div>
      ) : netHasInterface ? (
        <HostEntityLayer
          styles={styles}
          loading={netState.status === 'loading'}
          rows={netRows}
          onXRangeChange={dashboard.onXRangeChange}
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
            { key: 'net_bytes_recv_rate', label: 'bytes in', unit: 'byteps', color: HOST_PALETTE.blue },
            { key: 'net_bytes_sent_rate', label: 'bytes out', unit: 'byteps', color: HOST_PALETTE.emerald },
            { key: 'net_err_in_rate', label: 'err in', unit: 'cps', color: HOST_PALETTE.orange },
            { key: 'net_err_out_rate', label: 'err out', unit: 'cps', color: HOST_PALETTE.rose },
            { key: 'net_drop_in_rate', label: 'drop in', unit: 'cps', color: HOST_PALETTE.indigo },
            { key: 'net_drop_out_rate', label: 'drop out', unit: 'cps', color: HOST_PALETTE.neutral }
          ]}
        />
      ) : (
        <>
          <div className={styles.layerNote}>当前网络序列没有 interface 维度。下面是全接口合计，不是单网卡明细。</div>
          <FlexiblePanelSection styles={styles}>
            {renderTrend(networkChart, `${styles.span6} ${styles.compactTrend}`)}
            {renderTrend(networkErrorChart, `${styles.span6} ${styles.compactTrend}`)}
          </FlexiblePanelSection>
        </>
      )
    });
  }

  if (processReady) {
    tabItems.push({
      key: 'process',
      label: '进程',
      children: (
        <MetricViews
          monitorObjectId={dashboard.monitorObjectId}
          monitorObjectName={dashboard.monitorObjectName}
          instanceId={String(dashboard.instanceId || '')}
          instanceName={dashboard.resolvedInstanceName}
          idValues={dashboard.idValues}
          externalTimeValues={dashboard.timeValues}
          externalTimeDefaultValue={dashboard.timeDefaultValue}
          externalFrequence={dashboard.frequence}
          externalRefreshSignal={dashboard.metricsRefreshSignal}
          collectionInterval={dashboard.currentInstanceInterval}
          hideTimeSelector
          onExternalXRangeChange={dashboard.onXRangeChange}
          lockedPluginTab={HOST_PROCESS_METRICS_TAB}
        />
      )
    });
  }

  if (showGpu) {
    tabItems.push({
      key: 'gpu',
      label: 'GPU',
      children: gpuHasIndex ? (
        <HostEntityLayer
          styles={styles}
          loading={gpuState.status === 'loading'}
          rows={gpuRows}
          onXRangeChange={dashboard.onXRangeChange}
          columns={[
            { key: 'index', title: 'index', labelKey: 'index' },
            { key: 'nvidia_smi_utilization_memory', title: '显存%', unit: 'percent' },
            { key: 'nvidia_smi_temperature_gpu', title: '温度', unit: 'celsius' },
            { key: 'nvidia_smi_power_draw', title: '功耗', unit: 'watts' },
            { key: 'nvidia_smi_fan_speed_avg', title: '风扇%', unit: 'percent' }
          ]}
          chartMetrics={[
            { key: 'nvidia_smi_utilization_memory', label: '显存%', unit: 'percent', color: HOST_PALETTE.blue },
            { key: 'nvidia_smi_temperature_gpu', label: '温度', unit: 'celsius', color: HOST_PALETTE.rose },
            { key: 'nvidia_smi_power_draw', label: '功耗', unit: 'watts', color: HOST_PALETTE.amber },
            { key: 'nvidia_smi_fan_speed_avg', label: '风扇%', unit: 'percent', color: HOST_PALETTE.cyan }
          ]}
        />
      ) : (
        <div className={styles.layerNote}>已采到 GPU 序列，但没有 index 维度，因此不展开单卡表。</div>
      )
    });
  }

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} kpiCols={6} styles={styles} />
          <Tabs
            className={styles.hostTabs}
            activeKey={activeTab}
            onChange={setActiveTab}
            items={tabItems}
          />
        </>
      }
    />
  );
}
