'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Tabs } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import type { TimeValuesProps } from '@/app/monitor/types';
import { ProTimeWindowProvider } from '../../host/layered/pro-time-window';
import { selectProChartWindow } from '../../../shared/utils/pro-chart-window';
import HostAlertDrawer from '../../host/layered/host-alert-drawer';
import { hostAlertRailEvents, type HostAlertRailEvent } from '../../host/layered/events-rail';
import { overviewHostAlertParams } from '../../host/layered/host-alert-list';
import { GrayTabEmptyState } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import type { PostgresMetricMap } from './series';
import OverviewPane from './overview-pane';
import PerformancePane from './performance-pane';

type PostgresTab = 'overview' | 'performance' | 'statements' | 'waits' | 'replication';

const TABS: ReadonlyArray<{ key: PostgresTab; label: string; gray?: boolean }> = [
  { key: 'overview', label: '概览' },
  { key: 'performance', label: '性能' },
  { key: 'statements', label: 'Top SQL', gray: true },
  { key: 'waits', label: '等待', gray: true },
  { key: 'replication', label: '复制', gray: true }
];

const EMPTY_COPY: Record<'statements' | 'waits' | 'replication', { title: string; hint: string }> = {
  statements: {
    title: '当前实例未开启语句采集',
    hint: '开启 pg_stat_statements 类采集后，可在此查看 Top SQL；详见采集配置'
  },
  waits: {
    title: '当前实例未开启等待事件采集',
    hint: '开启后可在此查看等待事件并下钻；详见采集配置'
  },
  replication: {
    title: '流复制与复制槽采集未就绪',
    hint: '就绪后可查看复制延迟与槽积压；本盘暂不展示估算值'
  }
};

const isTab = (value: string | null): value is PostgresTab => (
  TABS.some((tab) => tab.key === value)
);

interface PostgresCategoryLayoutProps {
  instanceId: React.Key;
  monitorObjectId: React.Key;
  timeValues: TimeValuesProps;
  queryTimeRange: { startMs: number; endMs: number } | null;
  loading: boolean;
  pendingMetricNames: ReadonlySet<string>;
  metricMap: PostgresMetricMap;
}

export default function PostgresCategoryLayout({
  instanceId,
  monitorObjectId,
  timeValues,
  queryTimeRange,
  loading,
  pendingMetricNames,
  metricMap
}: PostgresCategoryLayoutProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getMonitorAlert } = useMonitorApi();
  const requested = searchParams.get('postgresTab');
  const tabFromUrl: PostgresTab = isTab(requested) ? requested : 'overview';
  const [tab, setTab] = useState<PostgresTab>(tabFromUrl);
  const [alertEvents, setAlertEvents] = useState<HostAlertRailEvent[]>([]);
  const [eventsPhase, setEventsPhase] = useState<'loading' | 'ready'>('loading');
  const eventsScopeRef = useRef<string | null>(null);
  const [alertDrawerOpen, setAlertDrawerOpen] = useState(false);
  const [alertRefreshKey, setAlertRefreshKey] = useState(0);
  const [focusAlertId, setFocusAlertId] = useState('');
  const instanceKey = String(instanceId || '');
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

  const selectTab = (next: PostgresTab, anchor?: string) => {
    setTab(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set('postgresTab', next);
    if (anchor) params.set('focus', anchor);
    else params.delete('focus');
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  useEffect(() => {
    if (tab !== 'performance') return;
    const anchor = searchParams.get('focus');
    if (!anchor) return;
    document.getElementById(`pg-zone-${anchor}`)?.scrollIntoView({ block: 'start' });
  }, [searchParams, tab]);

  useEffect(() => {
    if (eventsScopeRef.current === eventsScope) return;
    const first = eventsScopeRef.current == null;
    eventsScopeRef.current = eventsScope;
    if (first) return;
    setAlertEvents([]);
    setEventsPhase('loading');
  }, [eventsScope]);

  useEffect(() => {
    if (tab !== 'overview') return undefined;
    if (!instanceKey) {
      setAlertEvents([]);
      setEventsPhase('ready');
      return undefined;
    }
    let active = true;
    getMonitorAlert(overviewHostAlertParams(instanceKey))
      .then((data) => {
        if (!active) return;
        setAlertEvents(hostAlertRailEvents(data?.results));
        setEventsPhase('ready');
      })
      .catch(() => {
        if (!active) return;
        setAlertEvents([]);
        setEventsPhase('ready');
      });
    return () => {
      active = false;
    };
  }, [chartWindowKey, getMonitorAlert, instanceKey, tab]);

  const empty = tab === 'statements' || tab === 'waits' || tab === 'replication'
    ? EMPTY_COPY[tab]
    : null;

  return (
    <ProTimeWindowProvider
      timeValues={timeValues}
      queryTimeRange={queryTimeRange}
      suspend={loading && pendingMetricNames.size === 0}
    >
      <div className={host.root} data-postgres-pro="category">
        <div className={host.tabBand}>
          <Tabs
            className={host.partitionTabs}
            activeKey={tab}
            onChange={(key) => {
              if (isTab(key)) selectTab(key);
            }}
            items={TABS.map((item) => ({
              key: item.key,
              label: (
                <span
                  className={`${host.tabLabel}${item.gray ? ' !text-[var(--color-text-4)]' : ''}`}
                  data-postgres-tab={item.key}
                  data-postgres-tab-mode={item.gray ? 'empty' : 'ready'}
                >
                  {item.label}
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
              alertEvents={alertEvents}
              eventsLoading={eventsPhase === 'loading'}
              onOpenFocus={(anchor) => selectTab('performance', anchor)}
              onFocusAlert={(alertId) => {
                setFocusAlertId(alertId);
                setAlertDrawerOpen(true);
                setAlertRefreshKey((key) => key + 1);
              }}
            />
          ) : null}
          {tab === 'performance' ? (
            <PerformancePane metricMap={metricMap} pendingMetricNames={pendingMetricNames} />
          ) : null}
          {empty ? (
            <div data-postgres-empty={tab}>
              <GrayTabEmptyState title={empty.title} hint={empty.hint} />
            </div>
          ) : null}
        </div>
        <HostAlertDrawer
          open={alertDrawerOpen}
          refreshKey={alertRefreshKey}
          instanceId={instanceKey}
          monitorObjectId={monitorObjectId}
          focusAlertId={focusAlertId}
          onClose={() => setAlertDrawerOpen(false)}
          onCount={() => undefined}
          title="告警"
          footerHint="这里只列出当前实例尚未恢复的告警。"
          emptyCopy="当前无活跃告警"
          emptyHint="本实例暂无未恢复告警。"
        />
      </div>
    </ProTimeWindowProvider>
  );
}
