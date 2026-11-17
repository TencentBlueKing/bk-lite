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
import ConnectionsPane from './connections-pane';
import ThroughputPane from './throughput-pane';
import CachePane from './cache-pane';
import ReplicationPane from './replication-pane';
import { isMongoTab, mongoConnectionAnchor, MONGO_TABS, resolveMongoTab, type MongoTab } from './ia';
import {
  mongoReplicationDimmed,
  mongoReplicationLoad,
  mongoReplicationTabMode
} from './replication';
import type { MongoMetricMap } from './series';

const tabBadgeClass = (
  'ml-1 inline-flex h-[18px] items-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg)] px-1.5 text-[12px] font-normal leading-[18px] text-[var(--color-text-3)]'
);

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
  const focusFromUrl = searchParams.get('focus');
  const tabFromUrl = resolveMongoTab(requested, focusFromUrl);
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
    const resolved = resolveMongoTab(next, anchor ?? null);
    setTab(resolved);
    const params = new URLSearchParams(searchParams.toString());
    params.set('mongodbTab', resolved);
    if (anchor) params.set('focus', anchor);
    else params.delete('focus');
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  const query = searchParams.toString();
  useEffect(() => {
    if (requested !== 'throughput' || !mongoConnectionAnchor(focusFromUrl)) return;
    const params = new URLSearchParams(query);
    params.set('mongodbTab', 'connections');
    const next = params.toString();
    if (next === query) return;
    router.replace(`?${next}`, { scroll: false });
  }, [focusFromUrl, query, requested, router]);

  useEffect(() => {
    if (tab !== 'connections' && tab !== 'throughput' && tab !== 'cache') return;
    const anchor = searchParams.get('focus');
    if (!anchor) return;
    const id = anchor === 'docs-ops' ? 'mongo-documents' : `mongo-${anchor}`;
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

  const replicationBooting = loading && pendingMetricNames.size === 0;
  const replication = useMemo(
    () => mongoReplicationLoad(metricMap, pendingMetricNames, replicationBooting),
    [metricMap, pendingMetricNames, replicationBooting]
  );
  const replicationDimmed = mongoReplicationDimmed(replication);

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
            items={MONGO_TABS.map((item) => {
              const dimmed = item.key === 'replication' && replicationDimmed;
              const mode = item.key === 'replication' ? mongoReplicationTabMode(replication) : 'ready';
              return {
                key: item.key,
                label: (
                  <span
                    className={`${host.tabLabel}${dimmed ? ' !text-[var(--color-text-4)] [.ant-tabs-tab-active_&]:!text-[var(--color-text-1)]' : ''}`}
                    data-mongodb-tab={item.key}
                    data-mongodb-tab-mode={mode}
                  >
                    {item.label}
                    {dimmed ? <span className={tabBadgeClass}>未采集</span> : null}
                  </span>
                )
              };
            })}
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
          {tab === 'connections' ? (
            <ConnectionsPane metricMap={metricMap} pendingMetricNames={pendingMetricNames} />
          ) : null}
          {tab === 'throughput' ? (
            <ThroughputPane metricMap={metricMap} pendingMetricNames={pendingMetricNames} />
          ) : null}
          {tab === 'cache' ? (
            <CachePane metricMap={metricMap} pendingMetricNames={pendingMetricNames} />
          ) : null}
          {tab === 'replication' ? (
            <ReplicationPane
              metricMap={metricMap}
              pendingMetricNames={pendingMetricNames}
              booting={replicationBooting}
            />
          ) : null}
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
