'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Tabs } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { buildSearchParams, runWithConcurrency } from '../../../shared/utils';
import { selectProChartWindow } from '../../../shared/utils/pro-chart-window';
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
  reloadKey = 0
}: {
  instanceId: string;
  monitorObjectId: string | number;
  timeValues: TimeValuesProps;
  queryTimeRange?: { startMs: number; endMs: number } | null;
  instanceLoading?: boolean;
  intervalSeconds?: number;
  reloadKey?: number;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getInstanceQuery, getInstanceInstantQuery } = useViewApi();
  const { getMonitorAlert } = useMonitorApi();
  const [bundle, setBundle] = useState<NginxQueryResult>(EMPTY_RESULT);
  const [phase, setPhase] = useState<'loading' | 'ready'>('loading');
  const [nowSeconds, setNowSeconds] = useState(() => Date.now() / 1000);
  const [tab, setTab] = useState<NginxTabKey>('overview');
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [alertEvents, setAlertEvents] = useState<HostAlertRailEvent[]>([]);
  const [eventsPhase, setEventsPhase] = useState<'loading' | 'ready'>('loading');
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
    setPhase('loading');
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
  const timeKey = `${timeValues.timeRange.join(',')}|${timeValues.originValue ?? ''}|${reloadKey}`;
  useEffect(() => {
    if (instanceLoading) return undefined;
    if (!monitorObjectId || !instanceId) {
      setBundle(EMPTY_RESULT);
      setPhase('ready');
      return undefined;
    }
    let active = true;
    setPhase('loading');
    const context = { monitorObjectId, instanceId };
    const currentTime = timeValuesRef.current;
    runWithConcurrency([...NGINX_PRO_QUERIES], 4, async (spec) => {
      const params = buildSearchParams(
        spec.query,
        'none',
        [],
        [],
        currentTime,
        undefined,
        false,
        undefined,
        context
      );
      try {
        const result = spec.instant ? await getInstanceInstantQuery(params) : await getInstanceQuery(params);
        return { spec, result };
      } catch {
        return { spec, result: null };
      }
    }).then((rows) => {
      if (!active) return;
      const next: NginxQueryResult = { range: {}, instant: {} };
      rows.forEach((row) => {
        if (!row) return;
        if (row.spec.instant) next.instant[row.spec.key] = row.result ? readInstantSamples(row.result) : [];
        else next.range[row.spec.key] = row.result ? readRangeSeries(row.result) : [];
      });
      setBundle(next);
      setNowSeconds(Date.now() / 1000);
      setPhase('ready');
    });
    return () => {
      active = false;
    };
  }, [getInstanceInstantQuery, getInstanceQuery, instanceId, instanceLoading, monitorObjectId, timeKey]);

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
        setEventsPhase('ready');
        if (!alertDrawerOpenRef.current) setAlertCount(null);
      });
    return () => {
      active = false;
    };
  }, [chartWindowKey, getMonitorAlert, instanceId, instanceLoading]);

  const selectTab = (next: NginxTabKey) => {
    setTab(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set(TAB_QUERY, next);
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  const loading = phase === 'loading' || instanceLoading;
  const emptyText = model.collection.kind === 'not_onboarded' ? '尚未接入采集' : '暂无数据';
  const tabs: Array<{ key: NginxTabKey; label: string }> = [
    { key: 'overview', label: '概览' },
    { key: 'connections', label: '连接' }
  ];
  if (model.tabs.sites) tabs.push({ key: 'sites', label: '请求与站点' });
  if (model.tabs.upstream) tabs.push({ key: 'upstream', label: '上游' });
  const activeTab = tabs.some((item) => item.key === tab) ? tab : 'overview';

  return (
    <ProTimeWindowProvider timeValues={timeValues} queryTimeRange={queryTimeRange} suspend={loading}>
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
              loading={loading}
              emptyText={emptyText}
              alertCount={alertCount}
              alertsOpen={alertDrawerOpen}
              alertEvents={alertEvents}
              eventsLoading={eventsPhase === 'loading'}
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
            />
          ) : null}
          {activeTab === 'connections' ? (
            <ConnectionsPane model={model} loading={loading} emptyText={emptyText} />
          ) : null}
          {activeTab === 'sites' ? (
            <SitesPane model={model} loading={loading} emptyText={emptyText} />
          ) : null}
          {activeTab === 'upstream' ? (
            <UpstreamPane model={model} loading={loading} emptyText={emptyText} />
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
