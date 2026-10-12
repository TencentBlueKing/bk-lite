'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Tabs } from 'antd';
import useMonitorApi from '@/app/monitor/api';
import { buildLabelRows, buildMountDiskRows } from './entity-series';
import type { EntityTableRow } from './entity-series';
import type { HostDetailLayoutProps } from './detail-layout';
import type { EntityLoadState } from './use-entity-metrics';
import DiskPane, { countHotMounts } from './layered/disk-pane';
import FlatProcessSplit from './layered/flat-process-split';
import NetworkPane from './layered/network-pane';
import OverviewPane from './layered/overview-pane';
import SystemPane from './layered/system-pane';
import classic from './index.module.scss';
import styles from './layered/layered.module.scss';

const EMPTY_ENTITY: EntityLoadState = { status: 'idle', byMetric: {} };

const busiestFirst = (rows: EntityTableRow[]) => [...rows].sort((left, right) => {
  const score = (row: EntityTableRow) => (
    (row.values.net_bytes_recv_rate ?? 0) + (row.values.net_bytes_sent_rate ?? 0)
  );
  return score(right) - score(left);
});

const usePinnedRow = (rows: EntityTableRow[]) => {
  const [selectedKey, setSelectedKey] = useState('');
  const [pendingKey, setPendingKey] = useState('');
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

/** 分类仪表盘：概览 / 性能 / 磁盘 / 网络 / 进程。KPI 只在概览。 */
export default function HostCategoryLayout({
  dashboard,
  diskState,
  netState,
  processReady,
  processState = EMPTY_ENTITY,
  categoryTab = 'overview',
  onCategoryTabChange
}: HostDetailLayoutProps) {
  const { getMonitorAlert } = useMonitorApi();
  const [uncontrolledTab, setUncontrolledTab] = useState('overview');
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const activeTab = onCategoryTabChange ? categoryTab : uncontrolledTab;
  const setActiveTab = onCategoryTabChange || setUncontrolledTab;
  const metrics = dashboard.metricSeries;

  const diskRows = useMemo(() => buildMountDiskRows(diskState.byMetric), [diskState.byMetric]);
  const netRows = useMemo(
    () => busiestFirst(buildLabelRows(netState.byMetric, 'interface', 'net_bytes_recv_rate')),
    [netState.byMetric]
  );
  const processRows = useMemo(
    () => buildLabelRows(processState.byMetric, 'process_name', 'process_cpu_usage'),
    [processState.byMetric]
  );
  const diskSelection = usePinnedRow(diskRows);
  const netSelection = usePinnedRow(netRows);
  const processSelection = usePinnedRow(processRows);
  const diskLoading = diskState.status === 'idle' || diskState.status === 'loading';
  const netLoading = netState.status === 'idle' || netState.status === 'loading';
  const processLoading = processState.status === 'idle' || processState.status === 'loading';
  const hotMounts = diskRows.length ? countHotMounts(diskRows) : 0;

  useEffect(() => {
    if (activeTab === 'process' && !processReady) setActiveTab('overview');
  }, [activeTab, processReady, setActiveTab]);

  useEffect(() => {
    if (activeTab !== 'overview') return undefined;
    const instanceId = String(dashboard.instanceId || '');
    if (!instanceId) {
      setAlertCount(null);
      return undefined;
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
  }, [activeTab, dashboard.instanceId, getMonitorAlert]);

  const jump = (tab: 'disk' | 'net' | 'process', key: string) => {
    if (tab === 'disk') diskSelection.setPendingKey(key);
    if (tab === 'net') netSelection.setPendingKey(key);
    if (tab === 'process') processSelection.setPendingKey(key);
    setActiveTab(tab);
  };

  const tabItems = [
    { key: 'overview', label: '概览' },
    { key: 'system', label: '性能' },
    {
      key: 'disk',
      label: (
        <span className={styles.tabLabel}>
          磁盘
          {hotMounts > 0 ? <span className={styles.tabBadge}>{hotMounts}</span> : null}
        </span>
      )
    },
    { key: 'net', label: '网络' },
    ...(processReady ? [{ key: 'process', label: '进程' }] : [])
  ];

  const renderPane = () => {
    if (activeTab === 'system') {
      return (
        <SystemPane
          metrics={metrics}
          loading={dashboard.loading}
        />
      );
    }
    if (activeTab === 'disk') {
      return (
        <DiskPane
          rows={diskRows}
          loading={diskLoading}
          errorText={diskState.status === 'error' ? '磁盘数据加载失败，请稍后重试。' : undefined}
          selectedKey={diskSelection.selectedKey}
          onSelect={diskSelection.setSelectedKey}
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
        />
      );
    }
    return (
      <OverviewPane
        metrics={metrics}
        loading={dashboard.loading}
        diskRows={diskRows}
        diskLoading={diskLoading}
        netRows={netRows}
        processRows={processRows}
        processReady={processReady}
        alertCount={alertCount}
        monitorObjectId={dashboard.monitorObjectId}
        onJump={jump}
      />
    );
  };

  return (
    <div className={styles.root}>
      <Tabs
        className={`${classic.hostTabs} ${styles.partitionTabs}`}
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems.map((item) => ({ key: item.key, label: item.label }))}
      />
      <div className={styles.main}>{renderPane()}</div>
    </div>
  );
}
