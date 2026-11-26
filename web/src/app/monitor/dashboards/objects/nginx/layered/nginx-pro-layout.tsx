'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Tabs } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { buildSearchParams, runWithConcurrency } from '../../../shared/utils';
import { nginxCollectionIntervalSeconds } from '../rate-window';
import { selectProChartWindow } from '../../../shared/utils/pro-chart-window';
import { type NginxQueryPhase } from './query-phase';
import HostAlertDrawer from '../../host/layered/host-alert-drawer';
import { hostAlertRailEvents, type HostAlertRailEvent } from '../../host/layered/events-rail';
import { overviewHostAlertParams } from '../../host/layered/host-alert-list';
import { ProTimeWindowProvider } from '../../host/layered/pro-time-window';
import layered from '../../host/layered/layered.module.scss';
import { NGINX_PRO_QUERIES } from '../queries';
import ConnectionsPane from './connections-pane';
import { buildNginxDashboard, readInstantSamples, readRangeSeries, type NginxQueryResult } from './model';
import OverviewPane, { type NginxTabKey } from './overview-pane';
import SitesPane from './sites-pane';
import UpstreamPane from './upstream-pane';

const EMPTY_RESULT: NginxQueryResult = { range: {}, instant: {} };
const TAB_QUERY = 'nginxTab';

const isTab = (value: string | null): value is NginxTabKey => (
  value === 'overview' || value === 'connections' || value === 'sites' || value === 'upstream'
);

export default function NginxProLayout({
  instanceId,
  monitorObjectId,
  timeValues,
  queryTimeRange,
  instanceLoading = false,
  intervalSeconds,
  reloadKey = 0,
  linkedNodeId = '',
  linkedIp = ''
}: {
  instanceId: string;
  monitorObjectId: string | number;
  timeValues: TimeValuesProps;
  queryTimeRange?: { startMs: number; endMs: number } | null;
  instanceLoading?: boolean;
  intervalSeconds?: number;
  reloadKey?: number;
  linkedNodeId?: string;
  linkedIp?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getInstanceQuery, getInstanceInstantQuery } = useViewApi();
  const { getMonitorAlert } = useMonitorApi();
  const [bundle, setBundle] = useState<NginxQueryResult>(EMPTY_RESULT);
  const [phases, setPhases] = useState<Record<string, NginxQueryPhase>>({});
  const [nowSeconds, setNowSeconds] = useState(() => Date.now() / 1000);
  const [tab, setTab] = useState<NginxTabKey>('overview');
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [alertEvents, setAlertEvents] = useState<HostAlertRailEvent[]>([]);
  const [eventsPhase, setEventsPhase] = useState<NginxQueryPhase>('loading');
  const [alertRetry, setAlertRetry] = useState(0);
  const eventsScopeRef = useRef<string | null>(null);
  const [alertDrawerOpen, setAlertDrawerOpen] = useState(false);
  const alertDrawerOpenRef = useRef(false);
  alertDrawerOpenRef.current = alertDrawerOpen;
  const [alertRefreshKey, setAlertRefreshKey] = useState(0);
  const [focusAlertId, setFocusAlertId] = useState('');
  const [seenInstance, setSeenInstance] = useState(instanceId);
  if (instanceId !== seenInstance) {
    setSeenInstance(instanceId);
    setBundle(EMPTY_RESULT);
    setPhases({});
    setAlertCount(null);
    setAlertEvents([]);
    setFocusAlertId('');
    setTab('overview');
  }

  const requested = searchParams.get(TAB_QUERY);
  useEffect(() => {
    if (isTab(requested)) setTab(requested);
  }, [requested]);

  const timeValuesRef = useRef(timeValues);
  timeValuesRef.current = timeValues;
  const flightRef = useRef(0);
  const timeKey = `${timeValues.timeRange.join(',')}|${timeValues.originValue ?? ''}|${reloadKey}`;
  const loadQueries = useCallback((keys?: readonly string[]) => {
    if (instanceLoading) return undefined;
    if (!monitorObjectId || !instanceId) {
      setBundle(EMPTY_RESULT);
      setPhases(Object.fromEntries(NGINX_PRO_QUERIES.map((item) => [item.key, 'ready' as const])));
      return undefined;
    }
    const specs = keys
      ? NGINX_PRO_QUERIES.filter((item) => keys.includes(item.key))
      : [...NGINX_PRO_QUERIES];
    const ticket = keys ? flightRef.current : (flightRef.current + 1);
    if (!keys) flightRef.current = ticket;
    let cancelled = false;
    setPhases((current) => {
      const next = keys ? { ...current } : {};
      specs.forEach((item) => {
        next[item.key] = 'loading';
      });
      return next;
    });
    const context = { monitorObjectId, instanceId };
    const currentTime = timeValuesRef.current;
    const interval = nginxCollectionIntervalSeconds(intervalSeconds);
    runWithConcurrency(specs, 4, async (spec) => {
      const params = buildSearchParams(
        spec.query,
        'none',
        [],
        [],
        currentTime,
        undefined,
        false,
        interval,
        context,
        interval
      );
      try {
        const result = spec.instant ? await getInstanceInstantQuery(params) : await getInstanceQuery(params);
        return { spec, result, failed: false };
      } catch {
        return { spec, result: null, failed: true };
      }
    }).then((rows) => {
      if (cancelled || flightRef.current !== ticket) return;
      setBundle((current) => {
        const next: NginxQueryResult = keys
          ? { range: { ...current.range }, instant: { ...current.instant } }
          : { range: {}, instant: {} };
        rows.forEach((row) => {
          if (!row || row.failed) return;
          if (row.spec.instant) next.instant[row.spec.key] = row.result ? readInstantSamples(row.result) : [];
          else next.range[row.spec.key] = row.result ? readRangeSeries(row.result) : [];
        });
        return next;
      });
      setPhases((current) => {
        const next = { ...current };
        rows.forEach((row) => {
          if (!row) return;
          next[row.spec.key] = row.failed || row.result == null ? 'error' : 'ready';
        });
        return next;
      });
      setNowSeconds(Date.now() / 1000);
    });
    return () => {
      cancelled = true;
    };
  }, [getInstanceInstantQuery, getInstanceQuery, instanceId, instanceLoading, intervalSeconds, monitorObjectId]);
  useEffect(() => {
    const stop = loadQueries();
    return () => stop?.();
  }, [loadQueries, timeKey]);
  const retryKeys = (keys: readonly string[]) => {
    loadQueries(keys);
  };
  const retryFailed = () => {
    const failed = Object.entries(phases).filter(([, value]) => value === 'error').map(([key]) => key);
    if (failed.length) loadQueries(failed);
  };

  const model = useMemo(() => buildNginxDashboard({
    onboarded: Boolean(instanceId) && !instanceLoading,
    nowSeconds,
    intervalSeconds,
    data: bundle
  }), [bundle, instanceId, instanceLoading, intervalSeconds, nowSeconds]);

  useEffect(() => {
    if (tab === 'sites' && !model.tabs.sites) setTab('overview');
    if (tab === 'upstream' && !model.tabs.upstream) setTab('overview');
  }, [model.tabs.sites, model.tabs.upstream, tab]);

  const chartWindow = useMemo(
    () => selectProChartWindow(timeValues, queryTimeRange),
    [queryTimeRange, timeValues]
  );
  const chartWindowKey = chartWindow ? `${chartWindow.startSec}|${chartWindow.endSec}` : '';
  const eventsScope = `${instanceId}|${chartWindow ? Math.round(chartWindow.endSec - chartWindow.startSec) : ''}`;
  useEffect(() => {
    if (eventsScopeRef.current === eventsScope) return;
    const first = eventsScopeRef.current == null;
    eventsScopeRef.current = eventsScope;
    if (first) return;
    setAlertEvents([]);
    setEventsPhase('loading');
  }, [eventsScope]);

  useEffect(() => {
    if (!instanceId || instanceLoading) {
      setAlertCount(null);
      setAlertEvents([]);
      setEventsPhase('ready');
      return undefined;
    }
    let active = true;
    setEventsPhase('loading');
    getMonitorAlert(overviewHostAlertParams(instanceId))
      .then((data) => {
        if (!active) return;
        setAlertEvents(hostAlertRailEvents(data?.results));
        setEventsPhase('ready');
        if (!alertDrawerOpenRef.current) {
          setAlertCount(typeof data?.count === 'number' ? data.count : null);
        }
      })
      .catch(() => {
        if (!active) return;
        setAlertEvents([]);
        setEventsPhase('error');
        if (!alertDrawerOpenRef.current) setAlertCount(null);
      });
    return () => {
      active = false;
    };
  }, [alertRetry, chartWindowKey, getMonitorAlert, instanceId, instanceLoading]);

  const [anchor, setAnchor] = useState('');
  const selectTab = (next: NginxTabKey, nextAnchor?: string) => {
    setTab(next);
    setAnchor(nextAnchor || '');
    const params = new URLSearchParams(searchParams.toString());
    params.set(TAB_QUERY, next);
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  const emptyText = model.collection.kind === 'not_onboarded' ? '尚未接入采集' : '暂无数据';
  const tabs: Array<{ key: NginxTabKey; label: string }> = [
    { key: 'overview', label: '概览' },
    { key: 'connections', label: '连接' }
  ];
  if (model.tabs.sites) tabs.push({ key: 'sites', label: '请求与站点' });
  if (model.tabs.upstream) tabs.push({ key: 'upstream', label: '上游' });
  const activeTab = tabs.some((item) => item.key === tab) ? tab : 'overview';
  useEffect(() => {
    if (!anchor) return undefined;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(anchor)?.scrollIntoView({ block: 'start' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [anchor, activeTab]);

  return (
    <ProTimeWindowProvider timeValues={timeValues} queryTimeRange={queryTimeRange} suspend={instanceLoading}>
      <div className={layered.root} data-nginx-pro="category" data-nginx-collection={model.collection.kind}>
        <div className={layered.tabBand}>
          <Tabs
            className={layered.partitionTabs}
            activeKey={activeTab}
            onChange={(key) => selectTab(key as NginxTabKey)}
            items={tabs.map((item) => ({
              key: item.key,
              label: <span data-nginx-tab={item.key}>{item.label}</span>
            }))}
          />
        </div>
        <div className={layered.main} key={instanceId}>
          {activeTab === 'overview' ? (
            <OverviewPane
              model={model}
              phases={phases}
              alertPhase={eventsPhase}
              emptyText={emptyText}
              alertCount={alertCount}
              alertEvents={alertEvents}
              nodeId={linkedNodeId}
              ip={linkedIp}
              onOpenAlerts={() => {
                setFocusAlertId('');
                setAlertDrawerOpen(true);
                setAlertRefreshKey((key) => key + 1);
              }}
              onFocusAlert={(alertId) => {
                setFocusAlertId(alertId);
                setAlertDrawerOpen(true);
                setAlertRefreshKey((key) => key + 1);
              }}
              onOpen={selectTab}
              onRetry={retryKeys}
              onRetryFailed={retryFailed}
              onRetryAlerts={() => setAlertRetry((value) => value + 1)}
            />
          ) : null}
          {activeTab === 'connections' ? (
            <ConnectionsPane
              model={model}
              phases={phases}
              emptyText={emptyText}
              onRetry={retryKeys}
              onRetryFailed={retryFailed}
            />
          ) : null}
          {activeTab === 'sites' ? (
            <SitesPane
              model={model}
              phases={phases}
              emptyText={emptyText}
              onRetry={retryKeys}
              onRetryFailed={retryFailed}
            />
          ) : null}
          {activeTab === 'upstream' ? (
            <UpstreamPane
              model={model}
              phases={phases}
              emptyText={emptyText}
              onRetry={retryKeys}
              onRetryFailed={retryFailed}
            />
          ) : null}
        </div>
        <HostAlertDrawer
          open={alertDrawerOpen}
          refreshKey={alertRefreshKey}
          instanceId={instanceId}
          monitorObjectId={monitorObjectId}
          focusAlertId={focusAlertId}
          onClose={() => setAlertDrawerOpen(false)}
          onCount={setAlertCount}
          title="告警数量"
          footerHint="这里列出当前尚未恢复的告警。"
          emptyCopy="当前无活跃告警"
          emptyHint="这条 Nginx 没有尚未恢复的告警。"
        />
      </div>
    </ProTimeWindowProvider>
  );
}
