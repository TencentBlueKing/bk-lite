'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Progress, Segmented, Tooltip, Typography } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmPageBreadcrumb from '@/app/apm/components/apm-page-breadcrumb';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import Sparkline, { toSparklineData } from '@/app/apm/components/home/sparkline';
import {
  aggregateApplicationRedSeries,
  formatErrorRate,
  formatLatency,
  formatNumber,
  formatPerSecond,
  formatThroughput,
  isErrorRateDanger,
  type ApplicationRedSeriesPoint,
} from '@/app/apm/components/metric-format';
import {
  countActiveAlerts,
  expandServiceRows,
  indexEnabledSlos,
  isTimeWindow,
  metricKey,
  timeWindowRange,
  type TimeWindow,
} from '@/app/apm/components/service-catalog-model';
import TopologyCanvas from '@/app/apm/services/topology/topology-canvas';
import { focusApplicationTopology } from '@/app/apm/services/topology/topology-layout';
import type { ApmApplication, ApmEvent, ApmService, ApmServiceRed, ApmSlo, ApmTopologyGraph } from '@/app/apm/types';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';
type TopologySurfaceState = CatalogStateKind | 'ready';

interface KeyInfoItem {
  key: string;
  label: string;
  value: string;
  hint?: string;
  danger?: boolean;
}

interface KpiTileItem extends KeyInfoItem {
  detail?: string;
  trend?: number[];
  color: string;
}

function KpiTile({ item }: { item: KpiTileItem }) {
  return (
    <div
      className="flex min-w-0 flex-1 flex-col justify-between rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-2xs transition-all hover:border-[var(--color-primary)] hover:shadow-sm"
      data-kpi={item.key}
      data-kpi-trend={item.trend?.length ? 'true' : 'false'}
    >
      <div className="flex items-center justify-between gap-2">
        <Typography.Text type="secondary" className="!text-xs font-medium">
          {item.label}
        </Typography.Text>
        {item.detail ? (
          <Typography.Text type="secondary" className="!text-[11px] tabular-nums">
            {item.detail}
          </Typography.Text>
        ) : null}
      </div>
      <div className={`my-1 text-2xl font-bold tabular-nums tracking-tight ${item.danger ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-1)]'}`}>
        {item.value}
      </div>
      <div className="h-6 w-full pt-0.5">
        {item.trend?.length ? (
          <Sparkline color={item.color} data={item.trend} height={24} kind="area" fit="fill" fillOpacity={0.12} />
        ) : (
          <div className="h-6" />
        )}
      </div>
    </div>
  );
}

interface ApplicationEndpointRow {
  key: string;
  serviceName: string;
  environment: string;
  endpoint: string;
  request_rate: number;
  error_rate: number | null;
  p99_ms: number | null;
  ratio: number;
}

const TOP_ENDPOINT_LIMIT = 3;

function EndpointRankList({
  rows,
  emptyText,
  metricOf,
  strokeColor,
}: {
  rows: ApplicationEndpointRow[];
  emptyText: string;
  metricOf: (row: ApplicationEndpointRow) => string;
  strokeColor: string;
}) {
  if (!rows.length) {
    return <Typography.Text type="secondary" className="block py-3 text-center !text-xs">{emptyText}</Typography.Text>;
  }
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {rows.map((row) => (
        <li key={row.key} className="flex flex-col gap-0.5">
          <div className="flex items-start justify-between gap-2">
            <Link
              href={`/apm/explore/endpoints?${new URLSearchParams({ service: row.serviceName, environment: row.environment, endpoint: row.endpoint }).toString()}`}
              className="flex min-w-0 flex-col text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
              title={`${row.serviceName} ${row.endpoint}`}
            >
              <span className="truncate text-[11px] leading-4 text-[var(--color-text-3)]">{row.serviceName}</span>
              <span className="truncate font-mono text-xs leading-4">{row.endpoint}</span>
            </Link>
            <span className="shrink-0 text-xs font-medium tabular-nums leading-4 text-[var(--color-text-2)]">{metricOf(row)}</span>
          </div>
          <Progress className="!leading-none" percent={row.ratio} showInfo={false} size={['100%', 3]} strokeColor={strokeColor} trailColor="var(--color-border)" />
        </li>
      ))}
    </ul>
  );
}

export default function ApplicationObservability({
  applicationId,
  showAddIngest = false,
  parentHref = '/apm/services',
  parentLabel,
  parentAriaLabel,
}: {
  applicationId: string;
  showAddIngest?: boolean;
  parentHref?: string;
  parentLabel?: string;
  parentAriaLabel?: string;
}) {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const {
    getApplication,
    getServices,
    getServiceRed,
    getTopology,
    getEvents,
    getSlos,
    isLoading,
  } = useApmApi();
  const [application, setApplication] = useState<ApmApplication>();
  const [services, setServices] = useState<ApmService[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [graph, setGraph] = useState<ApmTopologyGraph>({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
  const [topologyState, setTopologyState] = useState<TopologySurfaceState>('loading');
  const [topologyRefreshKey, setTopologyRefreshKey] = useState(0);
  const [redMetrics, setRedMetrics] = useState<Record<string, ApmServiceRed>>({});
  const [metricFailureKeys, setMetricFailureKeys] = useState<string[]>([]);
  const [events, setEvents] = useState<ApmEvent[]>([]);
  const [slos, setSlos] = useState<ApmSlo[]>([]);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>(() => {
    const value = searchParams.get('window');
    return isTimeWindow(value) ? value : '1h';
  });
  const [metricRefreshKey, setMetricRefreshKey] = useState(0);

  useEffect(() => {
    if (isLoading || !applicationId) return;
    setState('loading');
    Promise.all([
      getApplication(applicationId),
      getServices(),
      getEvents({ limit: 100 }).catch(() => [] as ApmEvent[]),
      getSlos().catch(() => [] as ApmSlo[]),
    ])
      .then(([item, allServices, eventItems, sloItems]) => {
        setApplication(item);
        setServices(allServices.filter((service) => service.application_id === item.application_id));
        setEvents(eventItems);
        setSlos(sloItems);
        setState('ready');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [applicationId, getApplication, getEvents, getServices, getSlos, isLoading]);

  useEffect(() => {
    if (!application) return;
    const { startedAt, endedAt } = timeWindowRange(timeWindow);
    setTopologyState((current) => (current === 'ready' ? current : 'loading'));
    getTopology({
      started_at: startedAt.toISOString(),
      ended_at: endedAt.toISOString(),
      include_inferred: true,
      include_user_request: true,
    })
      .then((topology) => {
        const focused = focusApplicationTopology(topology, application.application_id).graph;
        setGraph(focused);
        setTopologyState(focused.nodes.length ? 'ready' : 'empty');
      })
      .catch((error) => {
        setGraph({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
        setTopologyState(catalogErrorKind(error));
      });
  }, [application, getTopology, timeWindow, topologyRefreshKey]);

  const rows = useMemo(() => expandServiceRows(services), [services]);

  useEffect(() => {
    const targets = rows.filter((row) => row.environment && !row.serviceArchivedAt);
    if (!targets.length) {
      setRedMetrics({});
      setMetricFailureKeys([]);
      return;
    }
    let active = true;
    const { startedAt, endedAt } = timeWindowRange(timeWindow);
    Promise.allSettled(targets.map(async (row) => ({
      key: metricKey(row.serviceId, row.environment),
      metric: await getServiceRed(row.serviceId, row.environment, startedAt.toISOString(), endedAt.toISOString()),
    })))
      .then((results) => {
        if (!active) return;
        setRedMetrics(Object.fromEntries(results.flatMap((result) => (
          result.status === 'fulfilled' ? [[result.value.key, result.value.metric]] : []
        ))));
        setMetricFailureKeys(results.flatMap((result, index) => (
          result.status === 'rejected'
            ? [metricKey(targets[index].serviceId, targets[index].environment)]
            : []
        )));
      });
    return () => {
      active = false;
    };
  }, [getServiceRed, metricRefreshKey, rows, timeWindow]);

  const alertCounts = useMemo(() => countActiveAlerts(events), [events]);
  const sloByServiceEnv = useMemo(() => indexEnabledSlos(slos), [slos]);
  const applicationAlertCount = useMemo(
    () => rows.reduce((sum, row) => sum + (alertCounts.get(`${row.serviceName}::${row.environment}`)?.count ?? 0), 0),
    [alertCounts, rows],
  );
  const applicationSloCount = useMemo(
    () => new Set(rows.filter((row) => sloByServiceEnv.has(metricKey(row.serviceId, row.environment))).map((row) => row.serviceId)).size,
    [rows, sloByServiceEnv],
  );

  const instrumentedServiceCount = useMemo(
    () => services.filter((service) => !service.archived_at).length,
    [services],
  );

  const keyInfo = useMemo<KeyInfoItem[]>(() => [
    {
      key: 'services',
      label: t('apm.applications.instrumentedServiceCount', '接入服务'),
      value: String(instrumentedServiceCount),
      hint: t('apm.applications.instrumentedServiceCountHint', '与应用卡片一致，只计本应用已接入的插桩服务；图上 Redis、PostgreSQL 等为推断下游，不计入'),
    },
    { key: 'alerts', label: t('apm.applications.alertCount', '告警数'), value: String(applicationAlertCount), danger: applicationAlertCount > 0 },
    { key: 'slo', label: t('apm.slo.title', 'SLO'), value: String(applicationSloCount) },
  ], [applicationAlertCount, applicationSloCount, instrumentedServiceCount, t]);

  const redSeries = useMemo<ApplicationRedSeriesPoint[]>(
    () => aggregateApplicationRedSeries(Object.values(redMetrics)),
    [redMetrics],
  );

  const kpis = useMemo<KpiTileItem[]>(() => {
    const metrics = Object.values(redMetrics);
    const requestRate = metrics.reduce((sum, red) => sum + (red.request_rate ?? 0), 0);
    const weightedErrors = metrics.reduce((sum, red) => sum + (red.request_rate ?? 0) * (red.error_rate ?? 0), 0);
    const errorRate = requestRate ? weightedErrors / requestRate : null;
    const worst = (pick: (red: ApmServiceRed) => number | null) => metrics.reduce<number | null>((max, red) => {
      const value = pick(red);
      return value == null ? max : Math.max(max ?? 0, value);
    }, null);
    const sumCount = (pick: (red: ApmServiceRed) => number | null) => metrics.reduce<number | null>((sum, red) => {
      const value = pick(red);
      return value == null ? sum : (sum ?? 0) + value;
    }, null);
    const requestCount = sumCount((red) => red.request_count);
    const errorCount = sumCount((red) => red.error_count);
    const trend = (pick: (point: ApplicationRedSeriesPoint) => number | null) => (
      redSeries.length >= 2 ? toSparklineData(redSeries.map(pick)) : undefined
    );
    return [
      {
        key: 'throughput',
        label: t('apm.common.throughput', '吞吐量'),
        value: formatPerSecond(formatThroughput(requestRate || null, false, t), t),
        detail: requestCount == null
          ? undefined
          : t('apm.applications.kpiRequestTotal', '{count} 请求', { count: formatNumber(requestCount) }),
        trend: trend((point) => point.request_rate),
        color: 'var(--color-primary)',
      },
      {
        key: 'error-rate',
        label: t('apm.common.errorRate', '错误率'),
        value: formatErrorRate(errorRate, false, t),
        detail: errorCount == null
          ? undefined
          : t('apm.applications.kpiErrorTotal', '{count} 错误', { count: formatNumber(errorCount) }),
        danger: isErrorRateDanger(errorRate),
        trend: trend((point) => point.error_rate_percent),
        color: 'var(--color-fail)',
      },
      {
        key: 'p95',
        label: t('apm.common.p95Latency', 'P95 延迟'),
        value: formatLatency(worst((red) => red.p95_ms), false, t),
        trend: trend((point) => point.p95_ms),
        color: 'var(--color-primary)',
      },
      {
        key: 'p99',
        label: t('apm.common.p99Latency', 'P99 延迟'),
        value: formatLatency(worst((red) => red.p99_ms), false, t),
        trend: trend((point) => point.p99_ms),
        color: 'var(--theme-color-status-warning)',
      },
    ];
  }, [redMetrics, redSeries, t]);

  const endpointRows = useMemo<Omit<ApplicationEndpointRow, 'ratio'>[]>(() => {
    const rowByKey = new Map(rows.map((row) => [metricKey(row.serviceId, row.environment), row]));
    return Object.entries(redMetrics).flatMap(([key, red]) => {
      const row = rowByKey.get(key);
      if (!row) return [];
      return (red.top_endpoints ?? []).map((item) => ({
        key: `${key}::${item.endpoint}`,
        serviceName: row.serviceName,
        environment: row.environment,
        endpoint: item.endpoint,
        request_rate: item.request_rate,
        error_rate: item.error_rate,
        p99_ms: item.p99_ms,
      }));
    });
  }, [redMetrics, rows]);

  const slowestEndpoints = useMemo<ApplicationEndpointRow[]>(() => {
    const items = endpointRows
      .filter((item) => item.p99_ms != null)
      .sort((left, right) => (right.p99_ms ?? 0) - (left.p99_ms ?? 0))
      .slice(0, TOP_ENDPOINT_LIMIT);
    const max = Math.max(...items.map((item) => item.p99_ms ?? 0), 1);
    return items.map((item) => ({ ...item, ratio: Math.round(((item.p99_ms ?? 0) / max) * 100) }));
  }, [endpointRows]);

  const errorEndpoints = useMemo<ApplicationEndpointRow[]>(() => {
    const items = endpointRows
      .filter((item) => (item.error_rate ?? 0) > 0)
      .sort((left, right) => (right.error_rate ?? 0) - (left.error_rate ?? 0))
      .slice(0, TOP_ENDPOINT_LIMIT);
    const max = Math.max(...items.map((item) => item.error_rate ?? 0), Number.EPSILON);
    return items.map((item) => ({ ...item, ratio: Math.round(((item.error_rate ?? 0) / max) * 100) }));
  }, [endpointRows]);

  const hasRedMetrics = Object.keys(redMetrics).length > 0;
  const panelClass = 'flex flex-col gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)]/40 p-3';
  const addIngestHref = application ? `/apm/integration/add?application_id=${encodeURIComponent(application.application_id)}` : '/apm/integration/add';

  return (
    <ApmRouteShell
      title={application?.name ?? t('apm.applications.detailTitle', '应用详情')}
      description={t('apm.applications.observabilityDescription', '查看应用拓扑、关键信息与重点指标。')}
      spacing="fill"
    >
      {state === 'ready' && application ? (
        <div className="flex flex-col gap-3 xl:h-full xl:min-h-0">
          <div className="grid gap-3 xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,1fr)_300px]">
            <ApmSurface className="flex min-h-[440px] min-w-0 flex-col overflow-hidden !rounded-xl shadow-2xs xl:min-h-0" padding="none">
              <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-3">
                <div className="min-w-0">
                  <ApmPageBreadcrumb
                    parentHref={parentHref}
                    parentLabel={parentLabel ?? t('apm.common.application', '应用')}
                    parentAriaLabel={parentAriaLabel ?? t('apm.applications.backToApplicationCatalog', '返回应用目录')}
                    current={(
                      <Typography.Title level={2} className="!mb-0 !truncate !text-base !font-semibold">
                        {application.name}
                      </Typography.Title>
                    )}
                  />
                </div>
                <div className="flex flex-wrap items-center gap-2.5">
                  <div className="flex items-center gap-1.5">
                    <Typography.Text type="secondary" className="!text-xs">{t('apm.common.timeWindow', '时间窗')}</Typography.Text>
                    <Segmented<TimeWindow>
                      aria-label={t('apm.services.metricWindow', '服务指标时间窗口')}
                      options={['15m', '1h', '4h', '1d', '7d']}
                      size="small"
                      value={timeWindow}
                      onChange={setTimeWindow}
                    />
                  </div>

                  {showAddIngest ? (
                    <>
                      <div className="h-4 w-px bg-[var(--color-border)]" aria-hidden="true" />
                      <Link href={addIngestHref}>
                        <Button type="primary" icon={<PlusOutlined aria-hidden="true" />} size="small">{t('apm.applications.addIngest', '添加接入')}</Button>
                      </Link>
                    </>
                  ) : null}
                </div>
              </div>
              {topologyState === 'ready' ? (
                <TopologyCanvas
                  edges={graph.edges}
                  fillHeight
                  focusNamespace={application.application_id}
                  keyword=""
                  layout="layered"
                  nodes={graph.nodes}
                  zoom={1}
                />
              ) : (
                <div className="flex min-h-[320px] flex-1 basis-0 items-center">
                  <div className="w-full">
                    <CatalogState
                      kind={topologyState}
                      description={topologyState === 'empty' ? t('apm.applications.noTopology', '当前时间窗暂无应用内调用关系。') : undefined}
                      onRetry={topologyState === 'forbidden' ? undefined : () => setTopologyRefreshKey((value) => value + 1)}
                    />
                  </div>
                </div>
              )}
            </ApmSurface>
            <ApmSurface className="flex min-w-0 flex-col gap-3 !rounded-xl shadow-2xs xl:min-h-0 xl:overflow-auto" padding="compact">
              <Typography.Text strong className="text-sm">{t('apm.applications.keyInfo', '关键信息')}</Typography.Text>
              <div className="grid grid-cols-3 gap-2">
                {keyInfo.map((item) => {
                  const card = (
                    <div className="flex min-w-0 flex-col gap-0.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)]/40 px-2.5 py-2" data-key-info={item.key}>
                      <Typography.Text type="secondary" className="truncate !text-[11px]">{item.label}</Typography.Text>
                      <div className={`text-lg font-semibold tabular-nums leading-tight ${item.danger ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-1)]'}`}>{item.value}</div>
                    </div>
                  );
                  return item.hint ? <Tooltip key={item.key} title={item.hint}>{card}</Tooltip> : <div key={item.key}>{card}</div>;
                })}
              </div>
              {!rows.length ? (
                <CatalogState
                  kind="empty"
                  description={t('apm.applications.noServices', '该应用还没有观测到服务。')}
                  action={showAddIngest ? (
                    <Link href={addIngestHref}>
                      <Button type="primary" size="small">{t('apm.applications.addIngest', '添加接入')}</Button>
                    </Link>
                  ) : undefined}
                />
              ) : (
                <>
                  <div className={panelClass}>
                    <Typography.Text strong className="!text-xs">{t('apm.applications.slowestEndpoints', '最慢端点')}</Typography.Text>
                    <EndpointRankList
                      rows={slowestEndpoints}
                      emptyText={t('apm.serviceDetail.noEndpoints', '当前时间窗暂无端点指标')}
                      metricOf={(row) => formatLatency(row.p99_ms, false, t)}
                      strokeColor="var(--color-primary)"
                    />
                  </div>
                  <div className={panelClass}>
                    <Typography.Text strong className="!text-xs">{t('apm.applications.errorEndpoints', '错误端点')}</Typography.Text>
                    <EndpointRankList
                      rows={errorEndpoints}
                      emptyText={t('apm.applications.noErrorEndpoints', '当前时间窗没有出错的端点')}
                      metricOf={(row) => formatErrorRate(row.error_rate, false, t)}
                      strokeColor="var(--color-fail)"
                    />
                  </div>
                </>
              )}
            </ApmSurface>
          </div>
          <div className="shrink-0" aria-label={t('apm.applications.keyMetrics', '重点指标')}>
            {metricFailureKeys.length ? (
              <div className="mb-2 flex justify-end">
                <Button
                  size="small"
                  type="link"
                  icon={<ReloadOutlined aria-hidden="true" />}
                  onClick={() => setMetricRefreshKey((value) => value + 1)}
                >
                  {t('apm.applications.partialMetricFailure', '{count} 个服务指标查询失败，重试', { count: metricFailureKeys.length })}
                </Button>
              </div>
            ) : null}
            {rows.length && !hasRedMetrics && metricFailureKeys.length ? (
              <ApmSurface className="!rounded-xl shadow-2xs" padding="normal">
                <CatalogState kind="error" onRetry={() => setMetricRefreshKey((value) => value + 1)} />
              </ApmSurface>
            ) : (
              <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                {kpis.map((item) => <KpiTile key={item.key} item={item} />)}
              </div>
            )}
          </div>
        </div>
      ) : (
        <ApmSurface padding="none">
          <CatalogState kind={state === 'ready' ? 'error' : state} />
        </ApmSurface>
      )}
    </ApmRouteShell>
  );
}
