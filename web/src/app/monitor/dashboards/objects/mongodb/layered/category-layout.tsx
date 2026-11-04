'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import ThroughputPane from './throughput-pane';
import CachePane from './cache-pane';
import ReplicationPane from './replication-pane';
import { isMongoTab, MONGO_TABS, resolveMongoTab, type MongoTab } from './ia';
import type { MongoMetricMap } from './series';

interface MongoCategoryLayoutProps {
  instanceId: React.Key;
  monitorObjectId: React.Key;
  timeValues: TimeValuesProps;
  queryTimeRange: { startMs: number; endMs: number } | null;
  loading: boolean;
  pendingMetricNames: ReadonlySet<string>;
  metricMap: MongoMetricMap;
}

export default function MongoCategoryLayout({
  instanceId,
  monitorObjectId,
  timeValues,
  queryTimeRange,
  loading,
  pendingMetricNames,
  metricMap
}: MongoCategoryLayoutProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getMonitorAlert } = useMonitorApi();
  const requested = searchParams.get('mongodbTab');
  const tabFromUrl = resolveMongoTab(requested);
  const [tab, setTab] = useState<MongoTab>(tabFromUrl);
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [alertEvents, setAlertEvents] = useState<HostAlertRailEvent[]>([]);
  const [eventsPhase, setEventsPhase] = useState<'loading' | 'ready'>('loading');
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

  const selectTab = (next: MongoTab, anchor?: string) => {
    setTab(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set('mongodbTab', next);
    if (anchor) params.set('focus', anchor);
    else params.delete('focus');
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  useEffect(() => {
    if (tab !== 'throughput' && tab !== 'cache') return;
    const anchor = searchParams.get('focus');
    if (!anchor) return;
    document.getElementById(`mongo-${anchor}`)?.scrollIntoView({ block: 'start' });
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
      setAlertCount(null);
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
        if (!alertDrawerOpenRef.current) setAlertCount(readAlertCount(data, 0));
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
  }, [chartWindowKey, getMonitorAlert, instanceKey, tab]);

  return (
    <ProTimeWindowProvider
      timeValues={timeValues}
      queryTimeRange={queryTimeRange}
      suspend={loading && pendingMetricNames.size === 0}
    >
      <div className={`${host.root} ${pageStyles.fitContent}`} data-mongodb-pro="category">
        <div className={host.tabBand}>
          <Tabs
            className={host.partitionTabs}
            activeKey={tab}
            onChange={(key) => {
              if (isMongoTab(key)) selectTab(key);
            }}
            items={MONGO_TABS.map((item) => ({
              key: item.key,
              label: (
                <span
                  className={`${host.tabLabel}${item.gray ? ' !text-[var(--color-text-4)] [.ant-tabs-tab-active_&]:!text-[var(--color-text-1)]' : ''}`}
                  data-mongodb-tab={item.key}
                  data-mongodb-tab-mode={item.gray ? 'gray' : 'ready'}
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
              alertCount={alertCount}
              alertsOpen={alertDrawerOpen}
              alertEvents={alertEvents}
              eventsLoading={eventsPhase === 'loading'}
              onOpenAlerts={openAlerts}
              onOpenTarget={selectTab}
              onFocusAlert={(alertId) => {
                setFocusAlertId(alertId);
                setAlertDrawerOpen(true);
                setAlertRefreshKey((key) => key + 1);
              }}
            />
          ) : null}
          {tab === 'throughput' ? (
            <ThroughputPane metricMap={metricMap} pendingMetricNames={pendingMetricNames} />
          ) : null}
          {tab === 'cache' ? (
            <CachePane metricMap={metricMap} pendingMetricNames={pendingMetricNames} />
          ) : null}
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
