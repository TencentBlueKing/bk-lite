'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Tabs } from 'antd';
import useMonitorApi from '@/app/monitor/api';
import type { TimeValuesProps } from '@/app/monitor/types';
import HostAlertDrawer from '../../host/layered/host-alert-drawer';
import { hostAlertRailEvents, type HostAlertRailEvent } from '../../host/layered/events-rail';
import { overviewHostAlertParams } from '../../host/layered/host-alert-list';
import { ProTimeWindowProvider } from '../../host/layered/pro-time-window';
import { selectProChartWindow } from '../../../shared/utils/pro-chart-window';
import type { PreparedSummaryCard } from '../../common/simple-dashboard-core';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import layered from '../../host/layered/layered.module.scss';
import OverviewPane from './overview-pane';
import type { RedisTopicTab } from './focus-pane';
import { CachePane, ConnThroughputPane, MemoryPane } from './topic-panes';
import { ClusterPane, ReplicationPane } from './architecture-panes';
import { replicationTabMode } from './architecture-state';
import { redisArchitectureView } from './architecture-view';
import { REDIS_REPLICATION_METRIC_NAMES } from './overview-metrics';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import { redisLatest, type RedisMetricMap } from './series';

type RedisContentTab = 'overview' | RedisTopicTab | 'replication' | 'cluster';

const TABS: ReadonlyArray<{ key: RedisContentTab; copy: RedisCategoryCopyKey }> = [
  { key: 'overview', copy: 'tabOverview' },
  { key: 'memory', copy: 'tabMemory' },
  { key: 'cache', copy: 'tabPerformance' },
  { key: 'connThroughput', copy: 'tabConnThroughput' },
  { key: 'replication', copy: 'tabReplication' },
  { key: 'cluster', copy: 'tabCluster' }
];

interface RedisCategoryLayoutProps {
  instanceId: React.Key;
  monitorObjectId: React.Key;
  timeValues: TimeValuesProps;
  queryTimeRange: { startMs: number; endMs: number } | null;
  loading: boolean;
  pendingMetricNames: ReadonlySet<string>;
  summaryCards: PreparedSummaryCard[];
  metricMap: RedisMetricMap;
}

export default function RedisCategoryLayout({
  instanceId,
  monitorObjectId,
  timeValues,
  queryTimeRange,
  loading,
  pendingMetricNames,
  summaryCards,
  metricMap
}: RedisCategoryLayoutProps) {
  const { t } = useDashboardText();
  const { getMonitorAlert } = useMonitorApi();
  const text = (key: RedisCategoryCopyKey) => redisCategoryText(t, key);
  const [tab, setTab] = useState<RedisContentTab>('overview');
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
    setAlertEvents([]);
    setFocusAlertId('');
  }
  const chartWindow = useMemo(
    () => selectProChartWindow(timeValues, queryTimeRange),
    [queryTimeRange, timeValues]
  );
  const chartWindowKey = chartWindow ? `${chartWindow.startSec}|${chartWindow.endSec}` : '';
  const eventsScope = `${instanceKey}|${
    chartWindow ? Math.round(chartWindow.endSec - chartWindow.startSec) : ''
  }`;
  const kpiLoading = (loading && pendingMetricNames.size === 0)
    || summaryCards.some((card) => pendingMetricNames.has(card.card.metric));
  const booting = loading && pendingMetricNames.size === 0;
  const replicationMode = replicationTabMode({
    hasPoint: REDIS_REPLICATION_METRIC_NAMES.some((name) => redisLatest(metricMap, name) != null),
    pending: REDIS_REPLICATION_METRIC_NAMES.some((name) => pendingMetricNames.has(name)),
    booting
  });
  const showCluster = redisArchitectureView({
    instanceKey,
    metricMap,
    pending: pendingMetricNames,
    booting
  }).kind === 'cluster';
  const openAlerts = useCallback(() => {
    setFocusAlertId('');
    setAlertDrawerOpen(true);
    setAlertRefreshKey((key) => key + 1);
  }, []);
  const visibleTabs = TABS.filter((item) => item.key !== 'cluster' || showCluster);
  const activeTab = visibleTabs.some((item) => item.key === tab) ? tab : 'overview';

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
  }, [chartWindowKey, getMonitorAlert, instanceKey, tab]);

  useEffect(() => {
    if (tab === 'cluster' && !showCluster) setTab('overview');
  }, [showCluster, tab]);

  return (
    <ProTimeWindowProvider
      timeValues={timeValues}
      queryTimeRange={queryTimeRange}
      suspend={loading && pendingMetricNames.size === 0}
    >
      <div
        className={layered.root}
        data-redis-pro="category"
        data-redis-alert-count={alertCount ?? undefined}
        data-redis-replication-mode={replicationMode}
        data-redis-cluster-tab={showCluster ? 'show' : 'hide'}
      >
        <div className={layered.tabBand}>
          <Tabs
            className={layered.partitionTabs}
            activeKey={activeTab}
            onChange={(key) => setTab(key as RedisContentTab)}
            items={visibleTabs.map((item) => {
              const gray = item.key === 'replication' && replicationMode === 'gray';
              return {
                key: item.key,
                label: (
                  <span
                    className={`${layered.tabLabel}${gray && tab !== item.key ? ' text-[var(--color-text-4)]' : ''}`}
                    data-redis-tab={item.key}
                    data-redis-tab-mode={item.key === 'replication' ? replicationMode : 'ready'}
                  >
                    {text(item.copy)}
                    {gray ? (
                      <span className="inline-flex h-[18px] items-center rounded-full border border-[var(--color-border)] px-1.5 text-[12px] font-normal leading-[18px] text-[var(--color-text-3)]">
                        {text('collectionNotReady')}
                      </span>
                    ) : null}
                  </span>
                )
              };
            })}
          />
        </div>
        <div className={layered.main}>
          {activeTab === 'overview' ? (
            <OverviewPane
              summaryCards={summaryCards}
              loading={kpiLoading}
              metricMap={metricMap}
              pendingMetricNames={pendingMetricNames}
              alertCount={alertCount}
              alertsOpen={alertDrawerOpen}
              alertEvents={alertEvents}
              eventsLoading={eventsPhase === 'loading'}
              onOpenAlerts={openAlerts}
              onFocusAlert={(alertId) => {
                setFocusAlertId(alertId);
                setAlertDrawerOpen(true);
                setAlertRefreshKey((key) => key + 1);
              }}
              onOpen={setTab}
            />
          ) : null}
          {activeTab === 'memory' ? (
            <MemoryPane metricMap={metricMap} pending={pendingMetricNames} />
          ) : null}
          {activeTab === 'cache' ? (
            <CachePane metricMap={metricMap} pending={pendingMetricNames} />
          ) : null}
          {activeTab === 'connThroughput' ? (
            <ConnThroughputPane metricMap={metricMap} pending={pendingMetricNames} />
          ) : null}
          {activeTab === 'replication' ? (
            <ReplicationPane
              metricMap={metricMap}
              pending={pendingMetricNames}
              mode={replicationMode}
            />
          ) : null}
          {activeTab === 'cluster' ? (
            <ClusterPane metricMap={metricMap} pending={pendingMetricNames} />
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
          title={text('alertTitle')}
          footerHint={text('alertFooter')}
          emptyCopy={text('alertEmpty')}
          emptyHint={text('alertEmptyHint')}
        />
      </div>
    </ProTimeWindowProvider>
  );
}
