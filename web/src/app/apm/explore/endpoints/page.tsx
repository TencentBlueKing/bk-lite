'use client';

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import {
  Alert,
  Button,
  Drawer,
  Input,
  Radio,
  Select,
  Space,
  Tag,
  theme,
  Typography,
  type TableColumnsType,
} from 'antd';
import FilterToolbar from '@/components/filter-toolbar';
import CompactEmptyState from '@/components/compact-empty-state';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import HealthDot from '@/app/apm/components/health-dot';
import {
  formatErrorRate,
  formatClockTime,
  formatDateTime,
  formatLatency,
  formatPerSecond,
  formatPercentage,
  formatRelativeTime,
  formatRequestRate,
  formatThroughput,
  isErrorRateDanger,
} from '@/app/apm/components/metric-format';
import type { ApmService, ApmServiceRed, ApmTraceSummary } from '@/app/apm/types';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import SummaryMetricCard from '@/components/summary-metric-card';
import TimeSeriesComposedChart from '@/components/time-series-composed-chart';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';
type MetricRange = '15m' | '1h' | '4h' | '1d' | '7d';
type SortKey = 'request_rate' | 'error_rate' | 'p95_ms';

interface EndpointRow {
  key: string;
  method: string;
  route: string;
  endpoint: string;
  serviceId: string;
  serviceName: string;
  namespace: string;
  environment: string;
  requestRate: number;
  errorRate: number | null;
  p95Ms: number | null;
  p99Ms: number | null;
  lastSeenAt: string;
}

const RANGE_MS: Record<MetricRange, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

const ENDPOINT_DRAWER_WIDTH = '56%';
const ENDPOINT_TREND_CHART_CELL_CLASS = 'flex h-64 min-w-0 max-w-full shrink-0 grow basis-64 flex-col overflow-hidden';
const ENDPOINT_METRIC_CARD_CLASS = 'min-w-0 max-w-full grow basis-36 overflow-hidden rounded-lg px-3 py-2.5';

function EndpointTrendChartCell({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className={ENDPOINT_TREND_CHART_CELL_CLASS}>
      <Typography.Text type="secondary" className="mb-2 block shrink-0 !text-xs">{title}</Typography.Text>
      <div className="min-h-0 min-w-0 flex-1">{children}</div>
    </div>
  );
}

const splitEndpoint = (value: string) => {
  const match = value.trim().match(/^([^\s]+)\s+(.+)$/);
  return match ? { method: match[1], route: match[2] } : { method: 'SPAN', route: value };
};

const errorRateColor = (value: number | null) => {
  if (value === null) return undefined;
  if (value >= 0.05) return 'error';
  if (value >= 0.01) return 'warning';
  return 'success';
};

export default function ApmEndpointsPage() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { getServiceRed, getServices, getTraces, isLoading: authLoading } = useApmApi();
  const [services, setServices] = useState<ApmService[]>([]);
  const [rows, setRows] = useState<EndpointRow[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [environment, setEnvironment] = useState('');
  const [timeRange, setTimeRange] = useState<MetricRange>('1h');
  const [serviceId, setServiceId] = useState('all');
  const [sortKey, setSortKey] = useState<SortKey>('request_rate');
  const [sortOrder, setSortOrder] = useState<'ascend' | 'descend'>('descend');
  const [keyword, setKeyword] = useState('');
  const [metricFailureCount, setMetricFailureCount] = useState(0);
  const [selected, setSelected] = useState<EndpointRow | null>(null);
  const [sampleTraces, setSampleTraces] = useState<ApmTraceSummary[]>([]);
  const [endpointRed, setEndpointRed] = useState<ApmServiceRed | null>(null);
  const [samplesLoading, setSamplesLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const load = useCallback(async () => {
    if (authLoading) return;
    setState('loading');
    setMetricFailureCount(0);
    try {
      const serviceItems = await getServices();
      setServices(serviceItems);
      const availableEnvironments = Array.from(new Set(
        serviceItems.flatMap((service) => service.environment_views.map((view) => view.environment)),
      )).filter(Boolean);
      const selectedEnvironment = environment || availableEnvironments[0] || 'production';
      if (!environment) setEnvironment(selectedEnvironment);

      const visibleServices = serviceItems.filter((service) => (
        service.environment_views.some((view) => view.environment === selectedEnvironment)
      ));
      const endedAt = new Date();
      const startedAt = new Date(endedAt.getTime() - RANGE_MS[timeRange]);
      const results = await Promise.allSettled(visibleServices.map(async (service) => ({
        service,
        red: await getServiceRed(service.id, selectedEnvironment, startedAt.toISOString(), endedAt.toISOString()),
      })));
      const successfulResults = results.filter((result) => result.status === 'fulfilled');
      if (results.length && !successfulResults.length) {
        const firstFailure = results.find((result) => result.status === 'rejected');
        throw firstFailure?.reason;
      }
      setMetricFailureCount(results.length - successfulResults.length);
      const endpointRows = results.flatMap((result) => {
        if (result.status !== 'fulfilled') return [];
        const { service, red } = result.value;
        return red.top_endpoints.map((endpoint) => {
          const identity = splitEndpoint(endpoint.endpoint);
          return {
            key: `${service.id}:${selectedEnvironment}:${endpoint.endpoint}`,
            method: identity.method,
            route: identity.route,
            endpoint: endpoint.endpoint,
            serviceId: service.id,
            serviceName: service.name,
            namespace: service.namespace,
            environment: selectedEnvironment,
            requestRate: endpoint.request_rate,
            errorRate: endpoint.error_rate,
            p95Ms: endpoint.p95_ms,
            p99Ms: endpoint.p99_ms,
            lastSeenAt: service.last_seen_at,
          };
        });
      });
      setRows(endpointRows);
      setState(endpointRows.length ? 'ready' : 'empty');
    } catch (error) {
      setRows([]);
      setMetricFailureCount(0);
      setState(catalogErrorKind(error));
    }
  }, [authLoading, environment, getServiceRed, getServices, timeRange]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selected) {
      setSampleTraces([]);
      setEndpointRed(null);
      return;
    }
    let active = true;
    setSamplesLoading(true);
    const endedAt = new Date();
    const startedAt = new Date(endedAt.getTime() - RANGE_MS[timeRange]);
    Promise.all([
      getTraces({
        service_namespace: selected.namespace,
        service_name: selected.serviceName,
        environment: selected.environment,
        span_name: selected.route,
        started_at: startedAt.toISOString(),
        ended_at: endedAt.toISOString(),
        limit: 20,
      }),
      getServiceRed(
        selected.serviceId,
        selected.environment,
        startedAt.toISOString(),
        endedAt.toISOString(),
        selected.endpoint,
      ),
    ])
      .then(([page, red]) => {
        if (!active) return;
        const matched = page.items.filter((item) => (
          item.root_span_name === selected.endpoint
          || item.root_span_name.includes(selected.route)
        ));
        setSampleTraces(matched.length ? matched : page.items.slice(0, 8));
        setEndpointRed(red);
      })
      .catch(() => {
        if (active) {
          setSampleTraces([]);
          setEndpointRed(null);
        }
      })
      .finally(() => {
        if (active) setSamplesLoading(false);
      });
    return () => {
      active = false;
    };
  }, [getServiceRed, getTraces, selected, timeRange]);

  const environmentOptions = useMemo(() => Array.from(new Set(
    services.flatMap((service) => service.environment_views.map((view) => view.environment)),
  )).filter(Boolean).map((value) => ({ value, label: value })), [services]);

  const serviceOptions = useMemo(() => services
    .filter((service) => service.environment_views.some((view) => view.environment === environment))
    .map((service) => ({ value: service.id, label: service.name })), [environment, services]);

  const visibleRows = useMemo(() => {
    const normalized = keyword.trim().toLocaleLowerCase();
    return rows
      .filter((row) => serviceId === 'all' || row.serviceId === serviceId)
      .filter((row) => !normalized
        || row.route.toLocaleLowerCase().includes(normalized)
        || row.serviceName.toLocaleLowerCase().includes(normalized))
      .sort((left, right) => {
        const direction = sortOrder === 'ascend' ? 1 : -1;
        if (sortKey === 'request_rate') return direction * (left.requestRate - right.requestRate);
        if (sortKey === 'error_rate') return direction * ((left.errorRate ?? -1) - (right.errorRate ?? -1));
        return direction * ((left.p95Ms ?? -1) - (right.p95Ms ?? -1));
      });
  }, [keyword, rows, serviceId, sortKey, sortOrder]);
  const pageRows = useMemo(
    () => visibleRows.slice((page - 1) * pageSize, page * pageSize),
    [page, pageSize, visibleRows],
  );

  const columns: TableColumnsType<EndpointRow> = [
    {
      title: t('apm.common.endpoint', '端点'),
      render: (_, row) => (
        <span className="inline-flex min-w-0 items-center gap-2">
          <span className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-xs font-medium ${
            row.method === 'POST'
              ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]'
              : 'bg-[var(--color-fill-1)] text-[var(--color-text-3)]'
          }`}
          >
            {row.method}
          </span>
          <EllipsisWithTooltip className="truncate font-mono text-xs" text={row.route} />
        </span>
      ),
    },
    {
      title: t('apm.explore.ownerService', '所属服务'),
      responsive: ['sm'],
      render: (_, row) => (
        <Space direction="vertical" size={0} className="min-w-0">
          <EllipsisWithTooltip className="truncate" text={row.serviceName} />
          <EllipsisWithTooltip className="truncate text-xs text-[var(--color-text-3)]" text={`${row.namespace || t('apm.common.unsetNamespace', '未设置 namespace')} · ${row.environment}`} />
        </Space>
      ),
    },
    {
      title: t('apm.common.throughput', '吞吐量'),
      dataIndex: 'requestRate',
      align: 'right',
      width: APM_TABLE_COLUMN_WIDTHS.metricWide,
      sorter: true,
      sortOrder: sortKey === 'request_rate' ? sortOrder : null,
      responsive: ['md'],
      render: (value) => (
        <span className="tabular-nums">
          <strong>{formatRequestRate(value, false, t)}</strong>
        </span>
      ),
    },
    {
      title: t('apm.common.errorRate', '错误率'),
      dataIndex: 'errorRate',
      align: 'right',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      sorter: true,
      sortOrder: sortKey === 'error_rate' ? sortOrder : null,
      responsive: ['md'],
      render: (value: number | null) => value === null
        ? '—'
        : <Tag bordered={false} color={errorRateColor(value)}>{formatErrorRate(value, false, t)}</Tag>,
    },
    {
      title: t('apm.common.p95', 'P95'),
      dataIndex: 'p95Ms',
      align: 'right',
      width: APM_TABLE_COLUMN_WIDTHS.compact,
      sorter: true,
      sortOrder: sortKey === 'p95_ms' ? sortOrder : null,
      responsive: ['lg'],
      render: (value: number | null) => <span className="tabular-nums">{formatLatency(value, false, t)}</span>,
    },
    {
      title: t('apm.common.lastSeen', '最近活跃'),
      dataIndex: 'lastSeenAt',
      align: 'right',
      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
      responsive: ['xl'],
      render: (value) => <Typography.Text type="secondary" className="text-xs">{formatRelativeTime(value, t)}</Typography.Text>,
    },
    {
      title: t('apm.common.operation', '操作'),
      key: 'actions',
      width: APM_TABLE_COLUMN_WIDTHS.singleAction,
      align: 'right',
      fixed: 'right',
      render: (_, row) => <Button className="!px-0" size="small" type="link" onClick={() => setSelected(row)}>{t('apm.common.view', '查看')}</Button>,
    },
  ];

  return (
    <ApmRouteShell
      title={t('apm.explore.endpointsTitle', '端点')}
      description={t('apm.explore.endpointsDescription', '按服务端点查看吞吐量、错误率与时延，通过查看操作打开详情与样本调用链。')}
      dependency="telemetry"
    >
      <div className="flex flex-col gap-3">
        {metricFailureCount ? (
          <Alert
            action={<Button icon={<ReloadOutlined aria-hidden="true" />} size="small" onClick={load}>{t('apm.common.retry', '重试')}</Button>}
            description={t('apm.explore.partialEndpointMetrics', '部分服务暂未返回端点指标，请稍后重试。')}
            message={t('apm.explore.metricFailureCount', '部分服务的端点指标查询失败（{count} 项）', { count: metricFailureCount })}
            showIcon
            type="warning"
          />
        ) : null}
        <ApmSurface>
          <div className="flex flex-col gap-4">
            <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
              <Input
                allowClear
                aria-label={t('apm.explore.searchEndpoint', '搜索路径模板或服务')}
                className="w-72"
                placeholder={t('apm.explore.searchEndpointPlaceholder', '搜索路径模板 / 服务')}
                prefix={<SearchOutlined aria-hidden="true" />}
                value={keyword}
                onChange={(event) => { setKeyword(event.target.value); setPage(1); }}
              />
              <Select
                aria-label={t('apm.common.service', '服务')}
                className="w-40"
                value={serviceId}
                options={[{ value: 'all', label: t('apm.common.allServices', '全部服务') }, ...serviceOptions]}
                onChange={(value) => { setServiceId(value); setPage(1); }}
              />
              <Select
                aria-label={t('apm.common.environment', '环境')}
                className="w-36"
                value={environment || undefined}
                placeholder={t('apm.common.selectEnvironment', '选择环境')}
                options={environmentOptions}
                onChange={(value) => {
                  setEnvironment(value);
                  setServiceId('all');
                  setPage(1);
                }}
              />
              <div className="flex-1" />
              <Radio.Group
                aria-label={t('apm.common.timeRange', '时间范围')}
                buttonStyle="solid"
                size="small"
                value={timeRange}
                onChange={(event) => setTimeRange(event.target.value)}
              >
                {(Object.keys(RANGE_MS) as MetricRange[]).map((value) => (
                  <Radio.Button key={value} value={value}>{value}</Radio.Button>
                ))}
              </Radio.Group>
              <Button aria-label={t('apm.explore.refreshEndpoints', '刷新端点')} icon={<ReloadOutlined aria-hidden="true" />} loading={state === 'loading'} onClick={load} />
            </FilterToolbar>
            {state === 'ready' || (state === 'loading' && rows.length > 0) ? (
              <ApmDataTable
              rowKey="key"
              size="middle"
              columns={columns}
              dataSource={pageRows}
              headerAlignment="column"
              loading={state === 'loading'}
              pagination={{
                current: page,
                pageSize,
                total: visibleRows.length,
                pageSizeOptions: [10, 20, 50, 100],
                showSizeChanger: true,
                onChange: (nextPage, nextPageSize) => {
                  setPage(nextPageSize === pageSize ? nextPage : 1);
                  setPageSize(nextPageSize);
                },
              }}
              onChange={(_, __, sorter) => {
                const activeSorter = Array.isArray(sorter) ? sorter[0] : sorter;
                if (!activeSorter?.order) return;
                const fieldMap: Record<string, SortKey> = {
                  requestRate: 'request_rate',
                  errorRate: 'error_rate',
                  p95Ms: 'p95_ms',
                };
                const nextKey = fieldMap[String(activeSorter.field)];
                if (!nextKey) return;
                setSortKey(nextKey);
                setSortOrder(activeSorter.order);
                setPage(1);
              }}
              />
            ) : (
              <CatalogState
                kind={state}
                description={state === 'empty' ? t('apm.explore.noEndpoints', '当前环境和时间范围内没有端点指标。') : undefined}
                onRetry={state === 'forbidden' ? undefined : load}
              />
            )}
          </div>
        </ApmSurface>
      </div>
      <Drawer
        width={ENDPOINT_DRAWER_WIDTH}
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? (
          <div>
            <div className="flex items-center gap-2">
              <span className={`rounded px-2 py-0.5 font-mono text-xs font-medium ${
                selected.method === 'POST'
                  ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]'
                  : 'bg-[var(--color-fill-1)] text-[var(--color-text-3)]'
              }`}
              >
                {selected.method}
              </span>
              <span className="font-mono text-sm">{selected.route}</span>
            </div>
            <Typography.Text type="secondary" className="!text-xs">
              {selected.serviceName} · {selected.environment} · {timeRange}
            </Typography.Text>
          </div>
        ) : null}
      >
        {selected ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-3">
              {[
                { label: t('apm.explore.throughputShort', '吞吐'), value: formatPerSecond(formatThroughput(selected.requestRate, false, t), t) },
                {
                  label: t('apm.common.errorRate', '错误率'),
                  value: formatErrorRate(selected.errorRate, false, t),
                  danger: isErrorRateDanger(selected.errorRate),
                },
                { label: t('apm.common.p95', 'P95'), value: formatLatency(selected.p95Ms, false, t) },
                { label: t('apm.common.p99', 'P99'), value: formatLatency(selected.p99Ms, false, t) },
              ].map((metric) => (
                <SummaryMetricCard
                  key={metric.label}
                  className={ENDPOINT_METRIC_CARD_CLASS}
                  label={metric.label}
                  labelClassName="!text-xs"
                  layout="vertical"
                  maxFontSize={16}
                  minFontSize={16}
                  value={metric.value}
                  valueColor={metric.danger ? 'var(--color-fail)' : undefined}
                />
              ))}
            </div>
            <div>
              <Typography.Text strong className="mb-2 block">{t('apm.explore.endpointTrend', '端点趋势')}</Typography.Text>
              <div className="flex flex-wrap gap-4" data-testid="endpoint-trend-charts">
                <EndpointTrendChartCell title={t('apm.common.throughput', '吞吐量')}>
                <TimeSeriesComposedChart
                  data={(endpointRed?.timeseries ?? []).map((point) => ({
                    ...point,
                    error_rate_percent: point.error_rate === null ? null : point.error_rate * 100,
                  }))}
                  xDataKey="timestamp"
                  getXLabel={(item) => formatClockTime(String(item.timestamp), false)}
                  xAxisBoundaryGap={false}
                  yAxes={[{ formatter: (value) => formatRequestRate(value, false, t) }]}
                  series={[{ name: t('apm.common.throughputReq', '吞吐量 req/s'), type: 'line', dataKey: 'request_rate', color: token.colorPrimary, showArea: true }]}
                  surfaceProps={{ emptyStateProps: { description: t('apm.explore.noEndpointTrend', '当前时间窗暂无端点趋势') } }}
                />
                </EndpointTrendChartCell>
                <EndpointTrendChartCell title={t('apm.common.errorRate', '错误率')}><TimeSeriesComposedChart data={(endpointRed?.timeseries ?? []).map((point) => ({ ...point, error_rate_percent: point.error_rate === null ? null : point.error_rate * 100 }))} xDataKey="timestamp" getXLabel={(item) => formatClockTime(String(item.timestamp), false)} xAxisBoundaryGap={false} yAxes={[{ formatter: (value) => formatPercentage(value, 1) }]} series={[{ name: t('apm.common.errorRatePercent', '错误率 %'), type: 'line', dataKey: 'error_rate_percent', color: token.colorError, showArea: true, showSymbol: true }]} surfaceProps={{ emptyStateProps: { description: t('apm.explore.noEndpointTrend', '当前时间窗暂无端点趋势') } }} /></EndpointTrendChartCell>
                <EndpointTrendChartCell title={t('apm.common.latency', '时延')}><TimeSeriesComposedChart data={(endpointRed?.timeseries ?? []).map((point) => ({ ...point }))} xDataKey="timestamp" getXLabel={(item) => formatClockTime(String(item.timestamp), false)} xAxisBoundaryGap={false} yAxes={[{ formatter: (value) => formatLatency(value, false, t) }]} series={[{ name: 'P95', type: 'line', dataKey: 'p95_ms', color: token.colorPrimary, showArea: true }, { name: 'P99', type: 'line', dataKey: 'p99_ms', color: token.colorWarning, lineType: 'dotted', showSymbol: true }]} surfaceProps={{ emptyStateProps: { description: t('apm.explore.noEndpointTrend', '当前时间窗暂无端点趋势') } }} /></EndpointTrendChartCell>
              </div>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <Typography.Text strong>{t('apm.explore.sampleTraces', '样本调用链')}</Typography.Text>
                <Link
                  href={`/apm/explore/traces?${new URLSearchParams({
                    service_namespace: selected.namespace,
                    service_name: selected.serviceName,
                    environment: selected.environment,
                  }).toString()}`}
                >
                  <Button type="link" size="small">{t('apm.explore.openInExplore', '在探索中打开')}</Button>
                </Link>
              </div>
              {samplesLoading ? (
                <CatalogState kind="loading" />
              ) : sampleTraces.length ? (
                <ApmDataTable
                  size="small"
                  rowKey="trace_id"
                  pagination={false}
                  dataSource={sampleTraces}
                  columns={[
                    {
                      title: 'Trace',
                      render: (_, item) => (
                        <Space size={6}>
                          <HealthDot level={item.status === 'error' ? 1 : 5} />
                          <Link href={`/apm/explore/traces/${item.trace_id}`} className="font-mono text-xs text-[var(--color-primary)]">
                            {item.trace_id.slice(0, 16)}…
                          </Link>
                        </Space>
                      ),
                    },
                    {
                      title: t('apm.explore.resource', '资源'),
                      dataIndex: 'root_span_name',
                      render: (value) => <span className="font-mono text-xs">{value}</span>,
                    },
                    {
                      title: t('apm.common.latency', '耗时'),
                      dataIndex: 'duration_ms',
                      width: APM_TABLE_COLUMN_WIDTHS.metric,
                      render: (value: number) => <span className="tabular-nums">{formatLatency(value, false, t)}</span>,
                    },
                    {
                      title: t('apm.common.time', '时间'),
                      dataIndex: 'started_at',
                      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
                      render: (value: string) => (
                        <span className="text-xs text-[var(--color-text-3)]">{formatRelativeTime(value, t)}</span>
                      ),
                    },
                  ]}
                />
              ) : (
                <CompactEmptyState description={t('apm.explore.noSampleTraces', '暂无匹配样本 Trace')} />
              )}
            </div>
            <Typography.Text type="secondary" className="!text-xs">
              {t('apm.explore.endpointSourceHint', '端点指标来自服务 RED Top endpoint 聚合；最近活跃参考服务发现时间 {time}。', { time: formatDateTime(selected.lastSeenAt) })}
            </Typography.Text>
          </div>
        ) : null}
      </Drawer>
    </ApmRouteShell>
  );
}
