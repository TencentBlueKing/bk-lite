'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Tabs } from 'antd';
import useMonitorApi from '@/app/monitor/api';
import {
  buildDiskDeviceRows,
  buildLabelRows,
  buildMountDiskRows,
  entitySeriesIndicatesWindows,
  pickDefaultDiskDeviceKey
} from './entity-series';
import type { EntityTableRow } from './entity-series';
import type { HostDetailLayoutProps } from './detail-layout';
import type { EntityLoadState } from './use-entity-metrics';
import DiskPane from './layered/disk-pane';
import FlatProcessSplit from './layered/flat-process-split';
import NetworkPane from './layered/network-pane';
import { hostAlertRailEvents, type HostAlertRailEvent } from './layered/events-rail';
import { ProTimeWindowProvider } from './layered/pro-time-window';
import { selectProChartWindow } from '../../shared/utils/pro-chart-window';
import HostAlertDrawer from './layered/host-alert-drawer';
import { overviewHostAlertParams } from './layered/host-alert-list';
import OverviewPane from './layered/overview-pane';
import SystemPane from './layered/system-pane';
import { latestNumber, latestPreferCount, resolveMemoryUsage } from './layered/readings';
import {
  loadPerCore,
  resolveHostSurfaceAlerts,
  resolveHostTabLevel,
  swapUsedPercent,
  type HostCategoryTab,
  type TabAlertLevel
} from './layered/tab-level';
import styles from './layered/layered.module.scss';

const TabLevelMark = ({ level }: { level: TabAlertLevel }) => {
  if (level === 'none') return null;
  return (
    <span
      className={`${styles.tabLevelDot} ${level === 'critical' ? styles.tabLevelCritical : styles.tabLevelWarn}`}
      role="img"
      aria-label={level === 'critical' ? '警告' : '提醒'}
    />
  );
};

const EMPTY_ENTITY: EntityLoadState = { status: 'idle', byMetric: {} };

/** 健康概览主值。这些序列或磁盘维度还在飞时，整行显示「加载中」，不用 `--` 占位。 */
const HOST_OVERVIEW_KPI_METRICS = [
  'cpu_usage_total',
  'mem_used_percent',
  'mem_available',
  'mem_total',
  'system_uptime',
  'system_load1'
] as const;

const maxRowValue = (rows: EntityTableRow[], key: string) => {
  let best: number | null = null;
  for (const row of rows) {
    const value = row.values[key];
    if (value == null || !Number.isFinite(value)) continue;
    if (best == null || value > best) best = value;
  }
  return best;
};

const busiestFirst = (rows: EntityTableRow[]) => [...rows].sort((left, right) => {
  const score = (row: EntityTableRow) => (
    (row.values.net_bytes_recv_rate ?? 0) + (row.values.net_bytes_sent_rate ?? 0)
  );
  return score(right) - score(left);
});

const usePinnedRow = (rows: EntityTableRow[], identity: string) => {
  const [selectedKey, setSelectedKey] = useState('');
  const [pendingKey, setPendingKey] = useState('');
  const [seenIdentity, setSeenIdentity] = useState(identity);
  if (identity !== seenIdentity) {
    setSeenIdentity(identity);
    setSelectedKey('');
    setPendingKey('');
  }
  useEffect(() => {
    if (!rows.length) return;
    if (pendingKey && rows.some((row) => row.key === pendingKey)) {
      setSelectedKey(pendingKey);
      setPendingKey('');
      return;
    }
    if (pendingKey) setPendingKey('');
    setSelectedKey((current) => (
      current && rows.some((row) => row.key === current) ? current : rows[0].key
    ));
  }, [pendingKey, rows]);
  return { selectedKey, setSelectedKey, setPendingKey };
};

/** 磁盘双选中：挂载与设备各自保持一行。设备只在首次或当前行失效时按挂载关联名默认。 */
const useDiskDualSelection = (
  mountRows: EntityTableRow[],
  deviceRows: EntityTableRow[],
  identity: string
) => {
  const [mountKey, setMountKey] = useState('');
  const [deviceKey, setDeviceKey] = useState('');
  const [pendingMountKey, setPendingMountKey] = useState('');
  const [devicePinned, setDevicePinned] = useState(false);
  const [seenIdentity, setSeenIdentity] = useState(identity);
  if (identity !== seenIdentity) {
    setSeenIdentity(identity);
    setMountKey('');
    setDeviceKey('');
    setPendingMountKey('');
    setDevicePinned(false);
  }

  const resolvedMountKey = (
    (pendingMountKey && mountRows.some((row) => row.key === pendingMountKey) ? pendingMountKey : '')
    || (mountKey && mountRows.some((row) => row.key === mountKey) ? mountKey : '')
    || mountRows[0]?.key
    || ''
  );
  const pinnedDeviceKey = devicePinned && deviceRows.some((row) => row.key === deviceKey) ? deviceKey : '';
  const resolvedDeviceKey = pinnedDeviceKey || pickDefaultDiskDeviceKey(mountRows, deviceRows, resolvedMountKey);

  useEffect(() => {
    if (pendingMountKey && mountRows.length && !mountRows.some((row) => row.key === pendingMountKey)) {
      setPendingMountKey('');
      return;
    }
    if (pendingMountKey && mountRows.some((row) => row.key === pendingMountKey)) {
      if (mountKey !== pendingMountKey) setMountKey(pendingMountKey);
      setPendingMountKey('');
      return;
    }
    if (resolvedMountKey && resolvedMountKey !== mountKey) setMountKey(resolvedMountKey);
  }, [mountKey, mountRows, pendingMountKey, resolvedMountKey]);

  useEffect(() => {
    if (!deviceRows.length) {
      if (devicePinned) setDevicePinned(false);
      if (deviceKey) setDeviceKey('');
      return;
    }
    if (devicePinned && deviceRows.some((row) => row.key === deviceKey)) return;
    if (!resolvedDeviceKey) return;
    setDeviceKey(resolvedDeviceKey);
    setDevicePinned(true);
  }, [deviceKey, devicePinned, deviceRows, resolvedDeviceKey]);

  const selectMount = (key: string) => {
    setPendingMountKey('');
    setMountKey(key);
  };

  const selectDevice = (key: string) => {
    setDeviceKey(key);
    setDevicePinned(true);
  };

  return {
    mountKey: resolvedMountKey,
    deviceKey: resolvedDeviceKey,
    selectMount,
    selectDevice,
    setPendingMountKey
  };
};

/** 专业仪表盘：概览 / 性能 / 磁盘 / 网络 / 进程。KPI 只在概览。 */
export default function HostCategoryLayout({
  dashboard,
  diskState,
  netState,
  processReady,
  processState = EMPTY_ENTITY,
  gpuState = EMPTY_ENTITY,
  categoryTab = 'overview',
  onCategoryTabChange
}: HostDetailLayoutProps) {
  const { getMonitorAlert } = useMonitorApi();
  const [uncontrolledTab, setUncontrolledTab] = useState('overview');
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [alertEvents, setAlertEvents] = useState<HostAlertRailEvent[]>([]);
  const [eventsPhase, setEventsPhase] = useState<'loading' | 'ready'>('loading');
  const eventsScopeRef = useRef<string | null>(null);
  const [alertDrawerOpen, setAlertDrawerOpen] = useState(false);
  const alertDrawerOpenRef = useRef(false);
  alertDrawerOpenRef.current = alertDrawerOpen;
  const [alertRefreshKey, setAlertRefreshKey] = useState(0);
  const [focusAlertId, setFocusAlertId] = useState('');
  const instanceKey = String(dashboard.instanceId || '');
  const [seenInstance, setSeenInstance] = useState(instanceKey);
  if (instanceKey !== seenInstance) {
    setSeenInstance(instanceKey);
    setAlertCount(null);
    setAlertEvents([]);
    setFocusAlertId('');
  }
  const openHostAlerts = useCallback(() => {
    setFocusAlertId('');
    setAlertDrawerOpen(true);
    setAlertRefreshKey((key) => key + 1);
  }, []);
  const focusHostAlert = useCallback((alertId: string) => {
    setFocusAlertId(alertId);
    setAlertDrawerOpen(true);
    setAlertRefreshKey((key) => key + 1);
  }, []);
  const applyAlertCount = useCallback((count: number) => {
    setAlertCount(count);
  }, []);
  const namedHost = String(dashboard.resolvedInstanceName || '').trim();
  const hostLabel = namedHost && namedHost !== '--'
    ? namedHost
    : String(dashboard.instanceId || '').trim();
  const activeTab = onCategoryTabChange ? categoryTab : uncontrolledTab;
  const setActiveTab = onCategoryTabChange || setUncontrolledTab;
  // 点「性能」时上一页的 Tooltip / Popover / 图表要先卸完，再挂性能 KPI。
  // 同一提交里卸门户又挂新图，rc-trigger 的测量占位 removeChild 会对不上父节点。
  const [performancePaneReady, setPerformancePaneReady] = useState(false);
  useEffect(() => {
    if (activeTab !== 'system') {
      setPerformancePaneReady(false);
      return undefined;
    }
    const frame = requestAnimationFrame(() => {
      setPerformancePaneReady(true);
    });
    return () => cancelAnimationFrame(frame);
  }, [activeTab]);
  const metrics = dashboard.metricSeries;
  const chartWindow = useMemo(
    () => selectProChartWindow(dashboard.timeValues, dashboard.queryTimeRange),
    [dashboard.queryTimeRange, dashboard.timeValues]
  );
  const chartWindowKey = chartWindow ? `${chartWindow.startSec}|${chartWindow.endSec}` : '';

  const diskRows = useMemo(() => buildMountDiskRows(diskState.byMetric), [diskState.byMetric]);
  const diskDeviceRows = useMemo(() => buildDiskDeviceRows(diskState.byMetric), [diskState.byMetric]);
  const windowsHost = dashboard.operatingSystem === 'windows' || entitySeriesIndicatesWindows(diskState.byMetric);
  const netRows = useMemo(
    () => busiestFirst(buildLabelRows(netState.byMetric, 'interface', 'net_bytes_recv_rate')),
    [netState.byMetric]
  );
  const processRows = useMemo(
    () => buildLabelRows(processState.byMetric, 'process_name', 'process_cpu_usage', ['pattern']),
    [processState.byMetric]
  );
  const gpuRows = useMemo(() => {
    const byIndex = buildLabelRows(gpuState.byMetric, 'index', 'nvidia_smi_utilization_gpu', ['name', 'uuid']);
    if (byIndex.length) return byIndex;
    const byName = buildLabelRows(gpuState.byMetric, 'name', 'nvidia_smi_utilization_gpu', ['uuid', 'index']);
    if (byName.length) return byName;
    return buildLabelRows(gpuState.byMetric, 'uuid', 'nvidia_smi_utilization_gpu', ['name', 'index']);
  }, [gpuState.byMetric]);
  const diskSelection = useDiskDualSelection(diskRows, diskDeviceRows, instanceKey);
  const netSelection = usePinnedRow(netRows, instanceKey);
  const processSelection = usePinnedRow(processRows, instanceKey);
  const diskLoading = diskState.status === 'idle' || diskState.status === 'loading';
  const netLoading = netState.status === 'idle' || netState.status === 'loading';
  const processLoading = processState.status === 'idle' || processState.status === 'loading';
  const tabReadings = useMemo(() => ({
    cpu_usage_total: latestNumber(metrics.cpu_usage_total),
    mem_used_percent: resolveMemoryUsage(
      metrics.mem_available?.viewData,
      metrics.mem_total?.viewData,
      metrics.mem_used_percent
    ).usedNow,
    disk_used_percent: maxRowValue(diskRows, 'disk_used_percent') ?? latestNumber(metrics.disk_used_percent),
    system_load1_per_core: loadPerCore(
      latestNumber(metrics.system_load1),
      latestNumber(metrics.cpu_n)
    ),
    system_uptime: latestNumber(metrics.system_uptime),
    mem_swap_used_percent: swapUsedPercent(
      latestNumber(metrics.host_mem_swap_used_bytes),
      latestNumber(metrics.host_mem_swap_total_bytes),
      latestNumber(metrics.mem_swap_free)
    ),
    processes_blocked: latestPreferCount(metrics.processes_blocked),
    processes_zombies: latestPreferCount(metrics.processes_zombies),
    process_cpu_usage: maxRowValue(processRows, 'process_cpu_usage'),
    process_mem_usage: maxRowValue(processRows, 'process_mem_usage')
  }), [diskRows, metrics, processRows]);
  const surfaceAlerts = useMemo(() => resolveHostSurfaceAlerts(tabReadings), [tabReadings]);

  useEffect(() => {
    if (activeTab === 'process' && !processReady) setActiveTab('overview');
  }, [activeTab, processReady, setActiveTab]);

  const eventsScope = `${String(dashboard.instanceId || '')}|${
    chartWindow ? Math.round(chartWindow.endSec - chartWindow.startSec) : ''
  }`;
  useEffect(() => {
    if (eventsScopeRef.current === eventsScope) return;
    const first = eventsScopeRef.current == null;
    eventsScopeRef.current = eventsScope;
    if (first) return;
    setAlertEvents([]);
    setEventsPhase('loading');
  }, [eventsScope]);

  useEffect(() => {
    if (activeTab !== 'overview') return undefined;
    const instanceId = String(dashboard.instanceId || '');
    if (!instanceId) {
      setAlertCount(null);
      setAlertEvents([]);
      setEventsPhase('ready');
      return undefined;
    }
    let active = true;
    getMonitorAlert(overviewHostAlertParams(instanceId))
      .then((data) => {
        if (!active) return;
        setAlertEvents(hostAlertRailEvents(data?.results));
        setEventsPhase('ready');
        if (!alertDrawerOpenRef.current) {
          setAlertCount(typeof data?.count === 'number' ? data.count : 0);
        }
      })
      .catch(() => {
        if (!active) return;
        setAlertEvents([]);
        setEventsPhase('ready');
        if (!alertDrawerOpenRef.current) setAlertCount(null);
      });
    return () => {
      active = false;
    };
  }, [activeTab, chartWindowKey, dashboard.instanceId, dashboard.loadTick, getMonitorAlert]);

  const jump = (tab: 'disk' | 'net' | 'process', key: string) => {
    if (tab === 'disk') diskSelection.setPendingMountKey(key);
    if (tab === 'net') netSelection.setPendingKey(key);
    if (tab === 'process') processSelection.setPendingKey(key);
    setActiveTab(tab);
  };

  const tabItems: Array<{ key: HostCategoryTab; label: string }> = [
    { key: 'overview', label: '概览' },
    { key: 'system', label: '性能' },
    { key: 'disk', label: '磁盘' },
    { key: 'net', label: '网络' },
    ...(processReady ? [{ key: 'process' as const, label: '进程' }] : [])
  ];

  const renderPane = () => {
    if (activeTab === 'system') {
      if (!performancePaneReady) {
        return (
          <div aria-busy="true" aria-live="polite">
            <div className={styles.sectionHead}>
              <div className={styles.sectionTitle}>关键指标</div>
            </div>
          </div>
        );
      }
      return (
        <SystemPane
          metrics={dashboard.metricSeries}
          pendingMetricNames={dashboard.pendingMetricNames}
          onRetryMetrics={dashboard.refetchMetricNames}
          alerts={surfaceAlerts.system}
          gpuRows={gpuRows}
          gpuLoading={gpuState.status === 'idle' || gpuState.status === 'loading'}
        />
      );
    }
    if (activeTab === 'disk') {
      return (
        <DiskPane
          mountRows={diskRows}
          deviceRows={diskDeviceRows}
          loading={diskLoading}
          errorText={diskState.status === 'error' ? '磁盘数据加载失败，请稍后重试。' : undefined}
          selectedMountKey={diskSelection.mountKey}
          selectedDeviceKey={diskSelection.deviceKey}
          onSelectMount={diskSelection.selectMount}
          onSelectDevice={diskSelection.selectDevice}
          windowsHost={windowsHost}
          hostLabel={hostLabel}
        />
      );
    }
    if (activeTab === 'net') {
      return (
        <NetworkPane
          rows={netRows}
          loading={netLoading}
          errorText={netState.status === 'error' ? '网卡数据加载失败，请稍后重试。' : undefined}
          selectedKey={netSelection.selectedKey}
          onSelect={netSelection.setSelectedKey}
          hostLabel={hostLabel}
        />
      );
    }
    if (activeTab === 'process' && processReady) {
      return (
        <FlatProcessSplit
          rows={processRows}
          loading={processLoading}
          selectedKey={processSelection.selectedKey}
          onSelect={processSelection.setSelectedKey}
          metrics={metrics}
          metricsLoading={dashboard.loading}
          hostLabel={hostLabel}
          alerts={surfaceAlerts.process}
        />
      );
    }
    return (
      <OverviewPane
        metrics={metrics}
        loading={
          (dashboard.loading && dashboard.pendingMetricNames.size === 0)
          || diskLoading
          || HOST_OVERVIEW_KPI_METRICS.some((name) => dashboard.pendingMetricNames.has(name))
        }
        pendingMetricNames={dashboard.pendingMetricNames}
        diskRows={diskRows}
        diskLoading={diskLoading}
        netRows={netRows}
        netLoading={netLoading}
        processRows={processRows}
        processReady={processReady}
        processLoading={processLoading}
        alertCount={alertCount}
        alertEvents={alertEvents}
        eventsLoading={eventsPhase === 'loading'}
        alertsOpen={alertDrawerOpen}
        onOpenAlerts={openHostAlerts}
        onFocusAlert={focusHostAlert}
        onJump={jump}
        alerts={surfaceAlerts.overview}
      />
    );
  };

  return (
    <ProTimeWindowProvider
      timeValues={dashboard.timeValues}
      queryTimeRange={dashboard.queryTimeRange}
      suspend={dashboard.loading && dashboard.pendingMetricNames.size === 0}
    >
    <div className={styles.root}>
      <div className={styles.tabBand}>
        <Tabs
          className={styles.partitionTabs}
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems.map((item) => ({
            key: item.key,
            label: (
              <span className={styles.tabLabel}>
                {item.label}
                <TabLevelMark level={resolveHostTabLevel(item.key, tabReadings)} />
              </span>
            )
          }))}
        />
      </div>
      <div className={styles.main}>{renderPane()}</div>
      <HostAlertDrawer
        open={alertDrawerOpen}
        refreshKey={alertRefreshKey}
        instanceId={String(dashboard.instanceId || '')}
        monitorObjectId={dashboard.monitorObjectId}
        focusAlertId={focusAlertId}
        onClose={() => setAlertDrawerOpen(false)}
        onCount={applyAlertCount}
      />
    </div>
    </ProTimeWindowProvider>
  );
}
