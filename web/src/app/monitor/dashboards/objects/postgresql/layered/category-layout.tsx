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
import useViewApi from '@/app/monitor/api/view';
import { asRangeQueryResult, buildSearchParams, toMetricSeries } from '../../../shared/utils';
import host from '../../host/layered/layered.module.scss';
import pageStyles from '../index.module.scss';
import { POSTGRES_DIGEST_METRICS } from '../queries';
import type { PostgresMetricMap } from './series';
import OverviewPane from './overview-pane';
import { CacheTxnPane, CheckpointAnomalyPane } from './performance-pane';
import { isPostgresTab, POSTGRES_TABS, postgresOpenTarget, resolvePostgresTab, type PostgresTab } from './ia';
import { StatementPane, WaitPane } from './digest-pane';
import ReplicationPane from './replication-pane';
import {
  postgresReplicationDimmed,
  postgresReplicationTabMode,
  readPostgresReplication
} from './replication';
import {
  postgresCollectionConfigPath,
  readPostgresDigestLoad,
  readPostgresStatementRows,
  readPostgresWaitRows,
  type PostgresDigestLoad,
  type PostgresStatementRow,
  type PostgresWaitRow
} from './digest';

interface PostgresCategoryLayoutProps {
  instanceId: React.Key;
  monitorObjectId: React.Key;
  instanceName: string;
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  queryTimeRange: { startMs: number; endMs: number } | null;
  loading: boolean;
  pendingMetricNames: ReadonlySet<string>;
  metricMap: PostgresMetricMap;
  reloadKey?: number;
  minStepSeconds?: number;
}

const tabBadgeClass = (
  'ml-1 inline-flex h-[18px] items-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg)] px-1.5 text-[12px] font-normal leading-[18px] text-[var(--color-text-3)]'
);

export default function PostgresCategoryLayout({
  instanceId,
  monitorObjectId,
  instanceName,
  idValues,
  instanceIdKeys,
  timeValues,
  queryTimeRange,
  loading,
  pendingMetricNames,
  metricMap,
  reloadKey = 0,
  minStepSeconds
}: PostgresCategoryLayoutProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getMonitorAlert } = useMonitorApi();
  const { getInstanceQuery, getInstanceInstantQuery } = useViewApi();
  const [statements, setStatements] = useState<PostgresStatementRow[]>([]);
  const [waits, setWaits] = useState<PostgresWaitRow[]>([]);
  const [digestStatus, setDigestStatus] = useState<'loading' | 'ready'>('loading');
  const [statementsLoad, setStatementsLoad] = useState<PostgresDigestLoad>('not_collected');
  const [waitsLoad, setWaitsLoad] = useState<PostgresDigestLoad>('not_collected');
  const [statementId, setStatementId] = useState('');
  const [waitId, setWaitId] = useState('');
  const requested = searchParams.get('postgresTab');
  const tabFromUrl = resolvePostgresTab(requested, searchParams.get('focus'));
  const [tab, setTab] = useState<PostgresTab>(tabFromUrl);
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

  const selectTab = (next: PostgresTab, anchor?: string) => {
    setTab(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set('postgresTab', next);
    if (anchor) params.set('focus', anchor);
    else params.delete('focus');
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  useEffect(() => {
    if (tab !== 'cache-txn' && tab !== 'checkpoint-anomaly') return;
    const anchor = searchParams.get('focus');
    if (!anchor) return;
    const target = document.getElementById(`pg-perf-${anchor}`)
      || document.getElementById(`pg-zone-${anchor}`);
    target?.scrollIntoView({ block: 'start' });
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

  const digestIdentity = `${idValues.join('\u0001')}::${instanceIdKeys.join('\u0001')}`;
  useEffect(() => {
    const [valueKey, keyKey = ''] = digestIdentity.split('::');
    const values = valueKey ? valueKey.split('\u0001') : [];
    const keys = keyKey ? keyKey.split('\u0001') : [];
    if (!monitorObjectId || !instanceId || !values.length) {
      setStatements([]);
      setWaits([]);
      setStatementsLoad('not_collected');
      setWaitsLoad('not_collected');
      setDigestStatus('ready');
      return undefined;
    }
    let active = true;
    setStatements([]);
    setWaits([]);
    setStatementsLoad('not_collected');
    setWaitsLoad('not_collected');
    setDigestStatus('loading');
    const context = { monitorObjectId: String(monitorObjectId), instanceId: String(instanceId) };
    const loadOne = (metric: (typeof POSTGRES_DIGEST_METRICS)[number]) => {
      const params = buildSearchParams(
        metric.query,
        metric.unit,
        values,
        keys,
        timeValues,
        undefined,
        false,
        minStepSeconds,
        context
      );
      const rangeQuery = Boolean(metric.range) || metric.query.includes('__$window__');
      const run = rangeQuery ? getInstanceQuery(params) : getInstanceInstantQuery(params);
      return run.then((result) => toMetricSeries(
        metric,
        rangeQuery ? result : asRangeQueryResult(result),
        instanceId,
        instanceName,
        values,
        keys
      )).catch(() => ({ ...metric, viewData: [], loadState: 'error' as const }));
    };
    Promise.all(POSTGRES_DIGEST_METRICS.map((metric) => loadOne(metric))).then((series) => {
      if (!active) return;
      const byName = Object.fromEntries(series.map((item) => [item.name, item]));
      const statementRows = readPostgresStatementRows(
        byName.postgresql_statement_time,
        byName.postgresql_statement_calls,
        byName.postgresql_statement_rows,
        byName.postgresql_statement_time_rate
      );
      const waitRows = readPostgresWaitRows(byName.postgresql_wait_sessions);
      setStatements(statementRows);
      setWaits(waitRows);
      setStatementsLoad(readPostgresDigestLoad(statementRows.length, [
        byName.postgresql_statement_time,
        byName.postgresql_statement_calls,
        byName.postgresql_statement_rows
      ]));
      setWaitsLoad(readPostgresDigestLoad(waitRows.length, [byName.postgresql_wait_sessions]));
      setDigestStatus('ready');
    });
    return () => {
      active = false;
    };
  }, [
    digestIdentity,
    getInstanceInstantQuery,
    getInstanceQuery,
    instanceId,
    instanceName,
    minStepSeconds,
    monitorObjectId,
    reloadKey,
    timeValues
  ]);

  const openCollectionConfig = () => {
    const objectId = typeof monitorObjectId === 'string' || typeof monitorObjectId === 'number'
      ? monitorObjectId
      : null;
    router.push(postgresCollectionConfigPath({
      monitorObjectId: objectId,
      instanceId: String(instanceId || ''),
      instanceName
    }));
  };

  const statementsDimmed = digestStatus === 'ready' && statementsLoad === 'not_collected';
  const waitsDimmed = digestStatus === 'ready' && waitsLoad === 'not_collected';
  const replicationBooting = loading && pendingMetricNames.size === 0;
  const replication = useMemo(
    () => readPostgresReplication(metricMap, pendingMetricNames, replicationBooting),
    [metricMap, pendingMetricNames, replicationBooting]
  );
  const replicationDimmed = postgresReplicationDimmed(replication.load);

  return (
    <ProTimeWindowProvider
      timeValues={timeValues}
      queryTimeRange={queryTimeRange}
      suspend={loading && pendingMetricNames.size === 0}
    >
      <div className={`${host.root} ${pageStyles.fitContent}`} data-postgres-pro="category">
        <div className={host.tabBand}>
          <Tabs
            className={host.partitionTabs}
            activeKey={tab}
            onChange={(key) => {
              if (isPostgresTab(key)) selectTab(key);
            }}
            items={POSTGRES_TABS.map((item) => {
              const dimmed = item.key === 'statements'
                ? statementsDimmed
                : item.key === 'waits'
                  ? waitsDimmed
                  : item.key === 'replication'
                    ? replicationDimmed
                    : false;
              const mode = item.key === 'statements'
                ? (statementsLoad === 'query_failed' ? 'failed' : statementsLoad === 'collected' ? 'ready' : 'empty')
                : item.key === 'waits'
                  ? (waitsLoad === 'query_failed' ? 'failed' : waitsLoad === 'collected' ? 'ready' : 'empty')
                  : item.key === 'replication'
                    ? postgresReplicationTabMode(replication.load)
                    : 'ready';
              return {
                key: item.key,
                label: (
                  <span
                    className={`${host.tabLabel}${dimmed ? ' !text-[var(--color-text-4)] [.ant-tabs-tab-active_&]:!text-[var(--color-text-1)]' : ''}`}
                    data-postgres-tab={item.key}
                    data-postgres-tab-mode={mode}
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
              onOpenFocus={(anchor) => {
                const target = postgresOpenTarget(anchor);
                selectTab(target.tab, target.anchor);
              }}
              onFocusAlert={(alertId) => {
                setFocusAlertId(alertId);
                setAlertDrawerOpen(true);
                setAlertRefreshKey((key) => key + 1);
              }}
            />
          ) : null}
          {tab === 'cache-txn' ? (
            <CacheTxnPane metricMap={metricMap} pendingMetricNames={pendingMetricNames} />
          ) : null}
          {tab === 'checkpoint-anomaly' ? (
            <CheckpointAnomalyPane metricMap={metricMap} pendingMetricNames={pendingMetricNames} />
          ) : null}
          {tab === 'statements' ? (
            <div data-postgres-empty={statementsLoad === 'collected' ? undefined : 'statements'}>
              <StatementPane
                rows={statements}
                selectedId={statementId}
                onSelect={setStatementId}
                loading={digestStatus === 'loading'}
                queryFailed={statementsLoad === 'query_failed'}
                instanceName={instanceName}
                onOpenCollection={openCollectionConfig}
              />
            </div>
          ) : null}
          {tab === 'waits' ? (
            <div data-postgres-empty={waitsLoad === 'collected' ? undefined : 'waits'}>
              <WaitPane
                rows={waits}
                selectedId={waitId}
                onSelect={setWaitId}
                loading={digestStatus === 'loading'}
                queryFailed={waitsLoad === 'query_failed'}
                instanceName={instanceName}
                onOpenCollection={openCollectionConfig}
              />
            </div>
          ) : null}
          {tab === 'replication' ? (
            <div className="w-full shrink-0" data-postgres-empty={replicationDimmed ? 'replication' : undefined}>
              <ReplicationPane
                metricMap={metricMap}
                pendingMetricNames={pendingMetricNames}
                booting={replicationBooting}
                onOpenCollection={openCollectionConfig}
              />
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
