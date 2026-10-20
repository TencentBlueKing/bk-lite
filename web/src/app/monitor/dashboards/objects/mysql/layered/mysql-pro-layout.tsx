'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Tabs } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { HOST_DASHBOARD_CONFIG } from '../../host/config';
import { latestNumber } from '../../host/layered/readings';
import HostAlertDrawer from '../../host/layered/host-alert-drawer';
import { hostAlertRailEvents, type HostAlertRailEvent } from '../../host/layered/events-rail';
import { activeHostAlertParams } from '../../host/layered/host-alert-list';
import {
  buildSearchParams,
  fetchDashboardInstancePages,
  resolveDashboardInstanceIdValues,
  toMetricSeries
} from '../../../shared/utils';
import { buildInstanceDisplayName } from '../../../shared/utils/instance';
import type { MetricSeries } from '../types';
import { MYSQL_DIGEST_METRICS } from '../queries';
import OverviewPane from './overview-pane';
import PerformancePane from './performance-pane';
import ReplicationPane from './replication-pane';
import { StatementPane, WaitPane } from './digest-pane';
import {
  MYSQL_IA_TABS,
  buildHostDashboardHref,
  hasStatementCollection,
  hasWaitCollection,
  isHostMonitorObject,
  isMysqlIaTab,
  matchMysqlHost,
  readMysqlOverview,
  readMysqlStatementRows,
  readMysqlWaitRows,
  type MysqlHostCandidate,
  type MysqlIaTab,
  type MysqlStatementRow,
  type MysqlWaitEventRow
} from './ia';
import host from '../../host/layered/layered.module.scss';
import pro from './pro.module.scss';

interface MysqlProLayoutProps {
  metricMap: Record<string, MetricSeries | undefined>;
  previousMetricMap: Record<string, MetricSeries | undefined>;
  loading: boolean;
  instanceId: string;
  monitorObjectId?: React.Key;
  nodeId: string;
  ip: string;
  instanceName: string;
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  minStepSeconds?: number;
}

const TAB_QUERY = 'mysqlTab';

const hostMetric = (name: string) => HOST_DASHBOARD_CONFIG.metrics.find((metric) => metric.name === name);

export default function MysqlProLayout({
  metricMap,
  previousMetricMap,
  loading,
  instanceId,
  monitorObjectId,
  nodeId,
  ip,
  instanceName,
  idValues,
  instanceIdKeys,
  timeValues,
  minStepSeconds
}: MysqlProLayoutProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getMonitorObject, getInstanceList, getMonitorAlert } = useMonitorApi();
  const { getInstanceQuery } = useViewApi();
  const [statements, setStatements] = useState<MysqlStatementRow[]>([]);
  const [waits, setWaits] = useState<MysqlWaitEventRow[]>([]);
  const [digestStatus, setDigestStatus] = useState<'loading' | 'ready'>('loading');
  const statementsCollected = hasStatementCollection(statements);
  const waitsCollected = hasWaitCollection(waits);
  const digestLoading = digestStatus === 'loading';
  const requestedTab = searchParams.get(TAB_QUERY);
  const tabFromUrl: MysqlIaTab = isMysqlIaTab(requestedTab) ? requestedTab : 'overview';
  const [tab, setTab] = useState<MysqlIaTab>(tabFromUrl);
  const [statementId, setStatementId] = useState('');
  const [waitId, setWaitId] = useState('');
  const [linkedHost, setLinkedHost] = useState<MysqlHostCandidate | null>(null);
  const [cpuPercent, setCpuPercent] = useState<number | null>(null);
  const [memPercent, setMemPercent] = useState<number | null>(null);
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [alertEvents, setAlertEvents] = useState<HostAlertRailEvent[]>([]);
  const [alertDrawerOpen, setAlertDrawerOpen] = useState(false);
  const [alertRefreshKey, setAlertRefreshKey] = useState(0);
  const [focusAlertId, setFocusAlertId] = useState('');

  const readings = useMemo(
    () => readMysqlOverview(metricMap, alertCount),
    [alertCount, metricMap]
  );
  const previous = useMemo(() => readMysqlOverview(previousMetricMap, null), [previousMetricMap]);

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
        document.getElementById(`mysql-perf-${anchor}`)?.scrollIntoView({ block: 'start' });
      });
    }
  };

  useEffect(() => {
    let active = true;
    if (!nodeId.trim() && !ip.trim()) {
      setLinkedHost(null);
      return undefined;
    }
    const load = async () => {
      try {
        const objects = await getMonitorObject({ include_invisible: true });
        if (!active || !Array.isArray(objects)) return;
        const hostObject = objects.find((item: { name?: string; display_name?: string }) => isHostMonitorObject(item));
        if (!hostObject?.id) {
          setLinkedHost(null);
          return;
        }
        const pages = await fetchDashboardInstancePages(getInstanceList, hostObject.id);
        if (!active) return;
        const keys = Array.isArray(hostObject.instance_id_keys) && hostObject.instance_id_keys.length
          ? hostObject.instance_id_keys.map((key: unknown) => String(key))
          : ['instance_id'];
        const hosts: MysqlHostCandidate[] = (pages.results || []).map((item) => {
          const row = item as {
            instance_id?: unknown;
            node_id?: unknown;
            ip?: unknown;
            instance_id_values?: unknown;
          };
          return {
            instanceId: String(row.instance_id || ''),
            name: buildInstanceDisplayName(row),
            nodeId: String(row.node_id || '').trim(),
            ip: String(row.ip || '').trim(),
            instanceIdValues: resolveDashboardInstanceIdValues(row),
            instanceIdKeys: keys,
            monitorObjectId: String(hostObject.id)
          };
        }).filter((host) => host.instanceId);
        setLinkedHost(matchMysqlHost({ nodeId, ip }, hosts));
      } catch {
        if (active) setLinkedHost(null);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [getInstanceList, getMonitorObject, ip, nodeId]);

  useEffect(() => {
    if (!linkedHost) {
      setCpuPercent(null);
      setMemPercent(null);
      return undefined;
    }
    const cpu = hostMetric('cpu_usage_total');
    const mem = hostMetric('mem_used_percent');
    if (!cpu || !mem || !linkedHost.instanceIdValues.length) {
      setCpuPercent(null);
      setMemPercent(null);
      return undefined;
    }
    let active = true;
    const context = {
      monitorObjectId: linkedHost.monitorObjectId,
      instanceId: linkedHost.instanceId
    };
    const loadOne = (metric: NonNullable<typeof cpu>) => getInstanceQuery(buildSearchParams(
      metric.query,
      metric.unit,
      linkedHost.instanceIdValues,
      linkedHost.instanceIdKeys,
      timeValues,
      undefined,
      false,
      minStepSeconds,
      context
    )).then((result) => latestNumber(toMetricSeries(
      metric,
      result,
      linkedHost.instanceId,
      linkedHost.name,
      linkedHost.instanceIdValues,
      linkedHost.instanceIdKeys
    ))).catch(() => null);

    Promise.all([loadOne(cpu), loadOne(mem)]).then(([cpuValue, memValue]) => {
      if (!active) return;
      setCpuPercent(cpuValue);
      setMemPercent(memValue);
    });
    return () => {
      active = false;
    };
  }, [getInstanceQuery, linkedHost, minStepSeconds, timeValues]);

  useEffect(() => {
    if (tab !== 'overview' || alertDrawerOpen) return undefined;
    if (!instanceId) {
      setAlertCount(null);
      return undefined;
    }
    let active = true;
    getMonitorAlert(activeHostAlertParams(instanceId, 1, 1))
      .then((data) => {
        if (active) setAlertCount(typeof data?.count === 'number' ? data.count : null);
      })
      .catch(() => {
        if (active) setAlertCount(null);
      });
    return () => {
      active = false;
    };
  }, [alertDrawerOpen, getMonitorAlert, instanceId, tab]);

  useEffect(() => {
    setAlertEvents([]);
  }, [instanceId]);

  useEffect(() => {
    if (tab !== 'overview') return undefined;
    if (!instanceId) {
      setAlertEvents([]);
      return undefined;
    }
    let active = true;
    getMonitorAlert({
      monitor_instance_id: instanceId,
      page: 1,
      page_size: 20
    })
      .then((data) => {
        if (active) setAlertEvents(hostAlertRailEvents(data?.results));
      })
      .catch(() => {
        if (active) setAlertEvents([]);
      });
    return () => {
      active = false;
    };
  }, [getMonitorAlert, instanceId, tab]);

  const digestIdentity = `${idValues.join('\u0001')}::${instanceIdKeys.join('\u0001')}`;
  useEffect(() => {
    const [valueKey, keyKey = ''] = digestIdentity.split('::');
    const values = valueKey ? valueKey.split('\u0001') : [];
    const keys = keyKey ? keyKey.split('\u0001') : [];
    if (!monitorObjectId || !instanceId || !values.length) {
      setStatements([]);
      setWaits([]);
      setDigestStatus('ready');
      return undefined;
    }
    let active = true;
    setDigestStatus('loading');
    const context = { monitorObjectId: String(monitorObjectId), instanceId };
    const loadOne = (metric: (typeof MYSQL_DIGEST_METRICS)[number]) => getInstanceQuery(buildSearchParams(
      metric.query,
      metric.unit,
      values,
      keys,
      timeValues,
      undefined,
      false,
      minStepSeconds,
      context
    )).then((result) => toMetricSeries(
      metric,
      result,
      instanceId,
      instanceName,
      values,
      keys
    )).catch(() => ({ ...metric, viewData: [], loadState: 'error' as const }));

    Promise.all(MYSQL_DIGEST_METRICS.map((metric) => loadOne(metric))).then((series) => {
      if (!active) return;
      const byName = Object.fromEntries(series.map((item) => [item.name, item]));
      setStatements(readMysqlStatementRows(
        byName.mysql_statement_time,
        byName.mysql_statement_calls,
        byName.mysql_statement_rows_examined
      ));
      setWaits(readMysqlWaitRows(
        byName.mysql_wait_event_count,
        byName.mysql_wait_event_time
      ));
      setDigestStatus('ready');
    });
    return () => {
      active = false;
    };
  }, [
    digestIdentity,
    getInstanceQuery,
    instanceId,
    instanceName,
    minStepSeconds,
    monitorObjectId,
    timeValues
  ]);

  const openStatement = (id: string) => {
    setStatementId(id);
    selectTab('statements');
  };

  const pane = () => {
    if (tab === 'performance') {
      return <PerformancePane metricMap={metricMap} loading={loading} />;
    }
    if (tab === 'replication') {
      return <ReplicationPane metricMap={metricMap} loading={loading} />;
    }
    if (tab === 'statements') {
      return (
        <StatementPane
          rows={statements}
          selectedId={statementId}
          onSelect={setStatementId}
          loading={digestLoading}
        />
      );
    }
    if (tab === 'waits') {
      return (
        <WaitPane
          rows={waits}
          statements={statements}
          loading={digestLoading}
          selectedId={waitId}
          onSelect={setWaitId}
          onOpenStatement={openStatement}
        />
      );
    }
    return (
      <OverviewPane
        readings={readings}
        previous={previous}
        metricMap={metricMap}
        loading={loading}
        statementsCollected={statementsCollected}
        host={linkedHost}
        hostHref={buildHostDashboardHref(linkedHost)}
        cpuPercent={cpuPercent}
        memPercent={memPercent}
        alertsOpen={alertDrawerOpen}
        alertEvents={alertEvents}
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
        onOpenFocus={(card) => selectTab(card.tab, card.anchor)}
      />
    );
  };

  return (
    <div className={host.root}>
      <div className={host.tabBand}>
        <Tabs
          className={host.partitionTabs}
          activeKey={tab}
          onChange={(key) => {
            if (isMysqlIaTab(key)) selectTab(key);
          }}
          items={MYSQL_IA_TABS.map((item) => {
            const dimmed = digestStatus === 'ready' && (
              (item.key === 'statements' && !statementsCollected)
              || (item.key === 'waits' && !waitsCollected)
            );
            return {
              key: item.key,
              label: (
                <span className={`${host.tabLabel}${dimmed ? ` ${pro.tabGhost}` : ''}`}>
                  {item.label}
                </span>
              )
            };
          })}
        />
      </div>
      <div className={host.main}>{pane()}</div>
      <HostAlertDrawer
        open={alertDrawerOpen}
        refreshKey={alertRefreshKey}
        instanceId={instanceId}
        monitorObjectId={monitorObjectId}
        focusAlertId={focusAlertId}
        onClose={() => setAlertDrawerOpen(false)}
        onCount={setAlertCount}
        emptyHint="本实例暂无活跃告警"
      />
    </div>
  );
}
