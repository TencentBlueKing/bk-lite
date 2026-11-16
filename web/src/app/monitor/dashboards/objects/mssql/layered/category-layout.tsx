'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type Key } from 'react';
import { Tabs } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import type { TimeValuesProps } from '@/app/monitor/types';
import { ProTimeWindowProvider } from '../../host/layered/pro-time-window';
import { selectProChartWindow } from '../../../shared/utils/pro-chart-window';
import HostAlertDrawer from '../../host/layered/host-alert-drawer';
import { hostAlertRailEvents, type HostAlertRailEvent } from '../../host/layered/events-rail';
import { overviewHostAlertParams, readAlertCount } from '../../host/layered/host-alert-list';
import host from '../../host/layered/layered.module.scss';
import pageStyles from '../index.module.scss';
import OverviewPane from './overview-pane';
import BufferPane from './buffer-pane';
import IoPane from './io-pane';
import WaitsPane from './waits-pane';
import { ReplicationPane, TopSqlPane } from './gray-panes';
import { isMssqlTab, MSSQL_TABS, mssqlFocusJump, mssqlKpiJump, resolveMssqlTab, type MssqlTab } from './ia';
import type { MssqlMetricMap } from './series';

const tabBadgeClass = (
  'ml-1 inline-flex h-[18px] items-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg)] px-1.5 text-[12px] font-normal leading-[18px] text-[var(--color-text-3)]'
);

interface MssqlCategoryLayoutProps {
  instanceId: Key;
  monitorObjectId: Key;
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  queryTimeRange: { startMs: number; endMs: number } | null;
  loading: boolean;
  pendingMetricNames: ReadonlySet<string>;
  metricMap: MssqlMetricMap;
  reloadKey?: number;
  minStepSeconds?: number;
}

export default function MssqlCategoryLayout({
  instanceId,
  monitorObjectId,
  idValues,
  instanceIdKeys,
  timeValues,
  queryTimeRange,
  loading,
  pendingMetricNames,
  metricMap,
  reloadKey = 0,
  minStepSeconds
}: MssqlCategoryLayoutProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getMonitorAlert } = useMonitorApi();
  const requested = searchParams.get('mssqlTab');
  const tabFromUrl = resolveMssqlTab(requested);
  const [tab, setTab] = useState<MssqlTab>(tabFromUrl);
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [alertEvents, setAlertEvents] = useState<HostAlertRailEvent[]>([]);
  const eventsScopeRef = useRef<string | null>(null);
  const [alertDrawerOpen, setAlertDrawerOpen] = useState(false);
  const alertDrawerOpenRef = useRef(false);
  alertDrawerOpenRef.current = alertDrawerOpen;
  const [alertRefreshKey, setAlertRefreshKey] = useState(0);
  const [focusAlertId, setFocusAlertId] = useState('');
  const instanceKey = String(instanceId || '');
  const [seenInstance, setSeenInstance] = useState(instanceKey);
  if (instanceKey !== seenInstance) {
    setSeenInstance(instanceKey);
    setAlertCount(null);
  }
  const openAlerts = useCallback(() => {
    setFocusAlertId('');
    setAlertDrawerOpen(true);
    setAlertRefreshKey((key) => key + 1);
  }, []);
  const chartWindow = useMemo(
    () => selectProChartWindow(timeValues, queryTimeRange),
    [queryTimeRange, timeValues]
  );
  const chartWindowKey = chartWindow ? `${chartWindow.startSec}|${chartWindow.endSec}` : '';
  const eventsScope = `${instanceKey}|${
    chartWindow ? Math.round(chartWindow.endSec - chartWindow.startSec) : ''
  }`;

  useEffect(() => {
    setTab(tabFromUrl);
  }, [tabFromUrl]);

  const selectTab = (next: MssqlTab, anchor?: string) => {
    setTab(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set('mssqlTab', next);
    if (anchor) params.set('focus', anchor);
    else params.delete('focus');
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  const openTarget = (anchor: string) => {
    const target = mssqlKpiJump(anchor) || mssqlFocusJump(anchor) || (
      anchor === 'connections' || anchor === 'batch' || anchor === 'cpu'
        ? { tab: 'overview' as const, anchor }
        : null
    );
    if (!target) return;
    selectTab(target.tab, target.anchor);
  };

  useEffect(() => {
    const anchor = searchParams.get('focus');
    if (!anchor) return undefined;
    const id = `mssql-${anchor}`;
    const scroll = () => document.getElementById(id)?.scrollIntoView({ block: 'start' });
    scroll();
    const frame = window.requestAnimationFrame(scroll);
    return () => window.cancelAnimationFrame(frame);
  }, [searchParams, tab]);

  useEffect(() => {
    if (eventsScopeRef.current === eventsScope) return;
    const first = eventsScopeRef.current == null;
    eventsScopeRef.current = eventsScope;
    if (first) return;
    setAlertEvents([]);
  }, [eventsScope]);

  useEffect(() => {
    if (tab !== 'overview') return undefined;
    if (!instanceKey) {
      setAlertCount(null);
      setAlertEvents([]);
      return undefined;
    }
    let active = true;
    getMonitorAlert(overviewHostAlertParams(instanceKey))
      .then((data) => {
        if (!active) return;
        setAlertEvents(hostAlertRailEvents(data?.results));
        if (!alertDrawerOpenRef.current) setAlertCount(readAlertCount(data, 0));
      })
      .catch(() => {
        if (!active) return;
        setAlertEvents([]);
        if (!alertDrawerOpenRef.current) setAlertCount(null);
      });
    return () => {
      active = false;
    };
  }, [chartWindowKey, getMonitorAlert, instanceKey, tab]);

  return (
    <ProTimeWindowProvider
      timeValues={timeValues}
      queryTimeRange={queryTimeRange}
      suspend={loading && pendingMetricNames.size === 0}
    >
      <div className={`${host.root} ${pageStyles.fitContent}`} data-mssql-pro="category">
        <div className={host.tabBand}>
          <Tabs
            className={host.partitionTabs}
            activeKey={tab}
            onChange={(key) => {
              if (isMssqlTab(key)) selectTab(key);
            }}
            items={MSSQL_TABS.map((item) => ({
              key: item.key,
              label: (
                <span
                  className={`${host.tabLabel}${item.dimmed ? ' !text-[var(--color-text-4)] [.ant-tabs-tab-active_&]:!text-[var(--color-text-1)]' : ''}`}
                  data-mssql-tab={item.key}
                  data-mssql-tab-mode={item.dimmed ? 'empty' : 'ready'}
                >
                  {item.label}
                  {item.dimmed ? <span className={tabBadgeClass}>未采集</span> : null}
                </span>
              )
            }))}
          />
        </div>
        <div className={host.main}>
          {tab === 'overview' ? (
            <OverviewPane
              metricMap={metricMap}
              pendingMetricNames={pendingMetricNames}
              booting={loading && pendingMetricNames.size === 0}
              alertCount={alertCount}
              alertsOpen={alertDrawerOpen}
              alertEvents={alertEvents}
              onOpenAlerts={openAlerts}
              onOpenFocus={openTarget}
              onFocusAlert={(alertId) => {
                setFocusAlertId(alertId);
                setAlertDrawerOpen(true);
                setAlertRefreshKey((key) => key + 1);
              }}
            />
          ) : null}
          {tab === 'buffer_memory' ? (
            <BufferPane metricMap={metricMap} pendingMetricNames={pendingMetricNames} />
          ) : null}
          {tab === 'io_storage' ? (
            <IoPane
              metricMap={metricMap}
              pendingMetricNames={pendingMetricNames}
              instanceId={instanceId}
              monitorObjectId={monitorObjectId}
              idValues={idValues}
              instanceIdKeys={instanceIdKeys}
              timeValues={timeValues}
              minStepSeconds={minStepSeconds}
              reloadKey={reloadKey}
            />
          ) : null}
          {tab === 'waits' ? (
            <WaitsPane
              metricMap={metricMap}
              pendingMetricNames={pendingMetricNames}
              instanceId={instanceId}
              monitorObjectId={monitorObjectId}
              idValues={idValues}
              instanceIdKeys={instanceIdKeys}
              timeValues={timeValues}
              minStepSeconds={minStepSeconds}
              reloadKey={reloadKey}
            />
          ) : null}
          {tab === 'top_sql' ? <TopSqlPane /> : null}
          {tab === 'replication' ? <ReplicationPane /> : null}
        </div>
        <HostAlertDrawer
          open={alertDrawerOpen}
          refreshKey={alertRefreshKey}
          instanceId={instanceKey}
          monitorObjectId={monitorObjectId}
          focusAlertId={focusAlertId}
          onClose={() => setAlertDrawerOpen(false)}
          onCount={setAlertCount}
          title="告警"
          footerHint="这里只列出当前实例尚未恢复的告警。"
          emptyCopy="当前无活跃告警"
          emptyHint="本实例暂无未恢复告警。"
        />
      </div>
    </ProTimeWindowProvider>
  );
}
