'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Tabs } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import HostAlertDrawer from '../../host/layered/host-alert-drawer';
import { hostAlertRailEvents, type HostAlertRailEvent } from '../../host/layered/events-rail';
import { ProTimeWindowProvider } from '../../host/layered/pro-time-window';
import { selectProChartWindow } from '../../../shared/utils/pro-chart-window';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { activeHostAlertParams, HOST_ALERT_PAGE_SIZE, normalizeHostAlerts } from '../../host/layered/host-alert-list';
import { mysqlCategoryText, type MysqlCategoryCopyKey } from './mysql-copy';
import {
  asRangeQueryResult,
  buildSearchParams,
  toMetricSeries
} from '../../../shared/utils';
import type { MetricSeries } from '../types';
import { MYSQL_DIGEST_METRICS } from '../queries';
import OverviewPane from './overview-pane';
import PerformancePane from './performance-pane';
import ReplicationPane from './replication-pane';
import { StatementPane, WaitPane } from './digest-pane';
import {
  MYSQL_IA_TABS,
  readMysqlDigestLoad,
  isMysqlIaTab,
  isSlowQueryAlertText,
  mysqlCollectionConfigPath,
  readMysqlOverview,
  readMysqlReplicationTabBadge,
  readMysqlStatementRows,
  readMysqlWaitRows,
  type MysqlDigestLoad,
  type MysqlIaTab,
  type MysqlStatementRow,
  type MysqlWaitEventRow
} from './ia';
import host from '../../host/layered/layered.module.scss';
import pro from './pro.module.scss';

interface MysqlProLayoutProps {
  metricMap: Record<string, MetricSeries | undefined>;
  previousMetricMap: Record<string, MetricSeries | undefined>;
  pendingMetricNames: ReadonlySet<string>;
  instanceId: string;
  monitorObjectId?: React.Key;
  instanceName: string;
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  queryTimeRange?: { startMs: number; endMs: number } | null;
  /** 刷新按钮。时间档位不变时也要按当前窗口重拉语句和等待。 */
  reloadKey?: number;
  minStepSeconds?: number;
}

const TAB_QUERY = 'mysqlTab';
const TAB_COPY: Record<MysqlIaTab, MysqlCategoryCopyKey> = {
  overview: 'tabOverview',
  performance: 'tabPerformance',
  replication: 'tabReplication',
  statements: 'tabStatements',
  waits: 'tabWaits'
};

export default function MysqlProLayout({
  metricMap,
  previousMetricMap,
  pendingMetricNames,
  instanceId,
  monitorObjectId,
  instanceName,
  idValues,
  instanceIdKeys,
  timeValues,
  queryTimeRange,
  reloadKey = 0,
  minStepSeconds
}: MysqlProLayoutProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useDashboardText();
  const { getMonitorAlert } = useMonitorApi();
  const { getInstanceQuery, getInstanceInstantQuery } = useViewApi();
  const [statements, setStatements] = useState<MysqlStatementRow[]>([]);
  const [waits, setWaits] = useState<MysqlWaitEventRow[]>([]);
  const [digestStatus, setDigestStatus] = useState<'loading' | 'ready'>('loading');
  const [statementsLoad, setStatementsLoad] = useState<MysqlDigestLoad>('not_collected');
  const [waitsLoad, setWaitsLoad] = useState<MysqlDigestLoad>('not_collected');
  const statementsCollected = statementsLoad === 'collected';
  const waitsCollected = waitsLoad === 'collected';
  const statementsQueryFailed = statementsLoad === 'query_failed';
  const waitsQueryFailed = waitsLoad === 'query_failed';
  const replicationBadge = useMemo(
    () => readMysqlReplicationTabBadge(metricMap, pendingMetricNames, instanceName),
    [instanceName, metricMap, pendingMetricNames]
  );
  const digestLoading = digestStatus === 'loading';
  const requestedTab = searchParams.get(TAB_QUERY);
  const tabFromUrl: MysqlIaTab = isMysqlIaTab(requestedTab) ? requestedTab : 'overview';
  const [tab, setTab] = useState<MysqlIaTab>(tabFromUrl);
  const [statementId, setStatementId] = useState('');
  const [waitId, setWaitId] = useState('');
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [slowAlertActive, setSlowAlertActive] = useState(false);
  const [alertEvents, setAlertEvents] = useState<HostAlertRailEvent[]>([]);
  const [eventsPhase, setEventsPhase] = useState<'loading' | 'ready'>('loading');
  const eventsScopeRef = useRef<string | null>(null);
  const [alertDrawerOpen, setAlertDrawerOpen] = useState(false);
  const [alertRefreshKey, setAlertRefreshKey] = useState(0);
  const [focusAlertId, setFocusAlertId] = useState('');

  const chartWindow = useMemo(
    () => selectProChartWindow(timeValues, queryTimeRange),
    [queryTimeRange, timeValues]
  );
  const chartWindowKey = chartWindow ? `${chartWindow.startSec}|${chartWindow.endSec}` : '';
  const readings = useMemo(
    () => readMysqlOverview(metricMap, alertCount),
    [alertCount, metricMap]
  );
  useEffect(() => {
    setTab(tabFromUrl);
  }, [tabFromUrl]);

  const selectTab = (next: MysqlIaTab, anchor?: string) => {
    setTab(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set(TAB_QUERY, next);
    if (anchor) params.set('focus', anchor);
    else params.delete('focus');
    router.replace(`?${params.toString()}`, { scroll: false });
    if (anchor) {
      window.requestAnimationFrame(() => {
        const named = document.getElementById(`mysql-perf-${anchor}`)
          || document.getElementById(anchor);
        const fallback = anchor === 'throughput'
          ? document.getElementById('mysql-perf-connections')
          : anchor === 'mysql-repl-trend'
            ? document.querySelector('[data-replication-state="ready"]')
            : null;
        (named || fallback)?.scrollIntoView({ block: 'start' });
      });
    }
  };

  const openStatements = () => {
    const top = statements[0];
    if (top) setStatementId(top.id);
    selectTab('statements');
  };

  const openCollectionConfig = () => {
    const objectId = typeof monitorObjectId === 'string' || typeof monitorObjectId === 'number'
      ? monitorObjectId
      : null;
    router.push(mysqlCollectionConfigPath({
      monitorObjectId: objectId,
      instanceId,
      instanceName
    }));
  };

  useEffect(() => {
    if (tab !== 'overview' || alertDrawerOpen) return undefined;
    if (!instanceId) {
      setAlertCount(null);
      setSlowAlertActive(false);
      return undefined;
    }
    let active = true;
    setSlowAlertActive(false);
    const loadAlerts = async () => {
      const pageSize = HOST_ALERT_PAGE_SIZE;
      let matched = false;
      let total = 0;
      for (let page = 1; page <= 4; page += 1) {
        const data = await getMonitorAlert(activeHostAlertParams(instanceId, page, pageSize));
        if (!active) return;
        if (page === 1) {
          total = typeof data?.count === 'number' ? data.count : 0;
          setAlertCount(typeof data?.count === 'number' ? data.count : null);
        }
        const rows = normalizeHostAlerts(data?.results);
        if (rows.some((row) => isSlowQueryAlertText(row.content, row.policy?.name || ''))) {
          matched = true;
          break;
        }
        if (rows.length === 0 || page * pageSize >= total) break;
      }
      if (active) setSlowAlertActive(matched);
    };
    loadAlerts().catch(() => {
      if (!active) return;
      setAlertCount(null);
      setSlowAlertActive(false);
    });
    return () => {
      active = false;
    };
  }, [alertDrawerOpen, getMonitorAlert, instanceId, tab]);

  const eventsScope = `${instanceId}|${
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
    if (tab !== 'overview') return undefined;
    if (!instanceId) {
      setAlertEvents([]);
      setEventsPhase('ready');
      return undefined;
    }
    let active = true;
    getMonitorAlert({
      monitor_instance_id: instanceId,
      page: 1,
      page_size: 20
    })
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
  }, [chartWindowKey, getMonitorAlert, instanceId, tab]);

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
    const context = { monitorObjectId: String(monitorObjectId), instanceId };
    const loadOne = (metric: (typeof MYSQL_DIGEST_METRICS)[number]) => {
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
      const rangeQuery = metric.query.includes('__$window__');
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

    Promise.all(MYSQL_DIGEST_METRICS.map((metric) => loadOne(metric))).then((series) => {
      if (!active) return;
      const byName = Object.fromEntries(series.map((item) => [item.name, item]));
      const statementRows = readMysqlStatementRows(
        byName.mysql_statement_time,
        byName.mysql_statement_calls,
        byName.mysql_statement_rows_examined,
        byName.mysql_statement_time_rate
      );
      const waitRows = readMysqlWaitRows(
        byName.mysql_wait_event_count,
        byName.mysql_wait_event_time,
        byName.mysql_wait_event_time_rate
      );
      setStatements(statementRows);
      setWaits(waitRows);
      setStatementsLoad(readMysqlDigestLoad(statementRows.length, [
        byName.mysql_statement_time,
        byName.mysql_statement_calls,
        byName.mysql_statement_rows_examined
      ]));
      setWaitsLoad(readMysqlDigestLoad(waitRows.length, [
        byName.mysql_wait_event_count,
        byName.mysql_wait_event_time
      ]));
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

  const pane = () => {
    if (tab === 'performance') {
      return <PerformancePane metricMap={metricMap} pendingMetricNames={pendingMetricNames} />;
    }
    if (tab === 'replication') {
      return (
        <ReplicationPane
          metricMap={metricMap}
          pendingMetricNames={pendingMetricNames}
          instanceName={instanceName}
          onOpenCollection={openCollectionConfig}
        />
      );
    }
    if (tab === 'statements') {
      return (
        <StatementPane
          rows={statements}
          waits={waits}
          selectedId={statementId}
          onSelect={setStatementId}
          loading={digestLoading}
          queryFailed={statementsQueryFailed}
          instanceName={instanceName}
          onOpenCollection={openCollectionConfig}
        />
      );
    }
    if (tab === 'waits') {
      return (
        <WaitPane
          rows={waits}
          statements={statements}
          loading={digestLoading}
          queryFailed={waitsQueryFailed}
          selectedId={waitId}
          onSelect={setWaitId}
          instanceName={instanceName}
          statementsCollected={statementsLoad !== 'not_collected'}
          onOpenCollection={openCollectionConfig}
        />
      );
    }
    return (
      <OverviewPane
        readings={readings}
        metricMap={metricMap}
        previousMetricMap={previousMetricMap}
        pendingMetricNames={pendingMetricNames}
        alertsOpen={alertDrawerOpen}
        alertEvents={alertEvents}
        eventsLoading={eventsPhase === 'loading'}
        slowAlertActive={slowAlertActive}
        instanceName={instanceName}
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
        onOpenFocus={(card) => {
          if (card.tab === 'statements') {
            openStatements();
            return;
          }
          selectTab(card.tab, card.anchor);
        }}
        onOpenHealthKpi={(next, anchor) => selectTab(next, anchor)}
      />
    );
  };

  return (
    <ProTimeWindowProvider timeValues={timeValues} queryTimeRange={queryTimeRange}>
    <div className={`${host.root} ${pro.fitContent}`}>
      <div className={host.tabBand}>
        <Tabs
          className={host.partitionTabs}
          activeKey={tab}
          onChange={(key) => {
            if (isMysqlIaTab(key)) selectTab(key);
          }}
          items={MYSQL_IA_TABS.map((item) => {
            const statementDimmed = digestStatus === 'ready' && (
              (item.key === 'statements' && !statementsCollected && !statementsQueryFailed)
              || (item.key === 'waits' && !waitsCollected && !waitsQueryFailed)
            );
            const replicationMark = item.key === 'replication' ? replicationBadge : null;
            const collectedGap = replicationMark === 'not_collected' || replicationMark === 'partial';
            const dimmed = statementDimmed || collectedGap;
            const badgeKey = statementDimmed
              ? 'notCollected'
              : replicationMark === 'unconfigured'
                ? 'replicationUnsupported'
                : collectedGap
                  ? 'notCollected'
                  : null;
            return {
              key: item.key,
              label: (
                <span className={`${host.tabLabel}${dimmed ? ` ${pro.tabGhost}` : ''}`}>
                  {mysqlCategoryText(t, TAB_COPY[item.key])}
                  {badgeKey ? (
                    <span className={pro.tabBadge}>{mysqlCategoryText(t, badgeKey)}</span>
                  ) : null}
                </span>
              )
            };
          })}
        />
      </div>
      <div className={`${host.main} ${pro.stackMain}`}>{pane()}</div>
      <HostAlertDrawer
        open={alertDrawerOpen}
        refreshKey={alertRefreshKey}
        instanceId={instanceId}
        monitorObjectId={monitorObjectId}
        focusAlertId={focusAlertId}
        onClose={() => setAlertDrawerOpen(false)}
        onCount={setAlertCount}
        title={mysqlCategoryText(t, 'alertTitle')}
        footerHint={mysqlCategoryText(t, 'alertFooter')}
        emptyCopy={mysqlCategoryText(t, 'alertEmpty')}
        emptyHint={mysqlCategoryText(t, 'alertEmptyHint')}
      />
    </div>
    </ProTimeWindowProvider>
  );
}
