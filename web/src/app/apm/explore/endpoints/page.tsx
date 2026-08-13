'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import {
  Alert,
  Button,
  Drawer,
  Empty,
  Input,
  Radio,
  Select,
  Space,
  Tag,
  Typography,
  type TableColumnsType,
} from 'antd';
import dayjs from 'dayjs';
import FilterToolbar from '@/components/filter-toolbar';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import HealthDot from '@/app/apm/components/health-dot';
import {
  formatErrorRate,
  formatLatency,
  formatRelativeTime,
  formatThroughput,
  isErrorRateDanger,
} from '@/app/apm/components/metric-format';
import type { ApmService, ApmTraceSummary } from '@/app/apm/types';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import SummaryMetricCard from '@/components/summary-metric-card';

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
  const { getServiceRed, getServices, getTraces, isLoading: authLoading } = useApmApi();
  const [services, setServices] = useState<ApmService[]>([]);
  const [rows, setRows] = useState<EndpointRow[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [environment, setEnvironment] = useState('');
  const [timeRange, setTimeRange] = useState<MetricRange>('1h');
  const [serviceId, setServiceId] = useState('all');
  const [sortKey, setSortKey] = useState<SortKey>('request_rate');
  const [keyword, setKeyword] = useState('');
  const [metricFailureCount, setMetricFailureCount] = useState(0);
  const [selected, setSelected] = useState<EndpointRow | null>(null);
  const [sampleTraces, setSampleTraces] = useState<ApmTraceSummary[]>([]);
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
      return;
    }
    let active = true;
    setSamplesLoading(true);
    const endedAt = new Date();
    const startedAt = new Date(endedAt.getTime() - RANGE_MS[timeRange]);
    getTraces({
      service_namespace: selected.namespace,
      service_name: selected.serviceName,
      environment: selected.environment,
      started_at: startedAt.toISOString(),
      ended_at: endedAt.toISOString(),
      limit: 20,
    })
      .then((page) => {
        if (!active) return;
        const matched = page.items.filter((item) => (
          item.root_span_name === selected.endpoint
          || item.root_span_name.includes(selected.route)
        ));
        setSampleTraces(matched.length ? matched : page.items.slice(0, 8));
      })
      .catch(() => {
        if (active) setSampleTraces([]);
      })
      .finally(() => {
        if (active) setSamplesLoading(false);
      });
    return () => {
      active = false;
    };
  }, [getTraces, selected, timeRange]);

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
        if (sortKey === 'request_rate') return right.requestRate - left.requestRate;
        if (sortKey === 'error_rate') return (right.errorRate ?? -1) - (left.errorRate ?? -1);
        return (right.p95Ms ?? -1) - (left.p95Ms ?? -1);
      });
  }, [keyword, rows, serviceId, sortKey]);
  const pageRows = useMemo(
    () => visibleRows.slice((page - 1) * pageSize, page * pageSize),
    [page, pageSize, visibleRows],
  );

  const columns: TableColumnsType<EndpointRow> = [
    {
      title: '方法',
      dataIndex: 'method',
      width: 80,
      render: (value) => (
        <span className={`rounded px-2 py-0.5 font-mono text-xs font-medium ${
          value === 'POST'
            ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]'
            : 'bg-[var(--color-fill-1)] text-[var(--color-text-3)]'
        }`}
        >
          {value}
        </span>
      ),
    },
    {
      title: '端点',
      render: (_, row) => (
        <span className="inline-flex min-w-0 items-center gap-2">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" aria-hidden="true" />
          <EllipsisWithTooltip className="truncate font-mono text-xs" text={`${row.method} ${row.route}`} />
        </span>
      ),
    },
    {
      title: '所属服务',
      width: 180,
      render: (_, row) => (
        <Space direction="vertical" size={0} className="min-w-0">
          <EllipsisWithTooltip className="truncate" text={row.serviceName} />
          <EllipsisWithTooltip className="truncate text-xs text-[var(--color-text-3)]" text={`${row.namespace || '未归类应用'} · ${row.environment}`} />
        </Space>
      ),
    },
    {
      title: '吞吐量',
      dataIndex: 'requestRate',
      align: 'right',
      width: 130,
      render: (value) => (
        <span className="tabular-nums">
          <strong>{formatThroughput(value)}</strong>
          {' '}
          <Typography.Text type="secondary" className="text-xs">/s</Typography.Text>
        </span>
      ),
    },
    {
      title: '错误率',
      dataIndex: 'errorRate',
      align: 'right',
      width: 100,
      render: (value: number | null) => value === null
        ? '—'
        : <Tag bordered={false} color={errorRateColor(value)}>{formatErrorRate(value)}</Tag>,
    },
    {
      title: 'P95',
      dataIndex: 'p95Ms',
      align: 'right',
      width: 100,
      render: (value: number | null) => <span className="tabular-nums">{formatLatency(value)}</span>,
    },
    {
      title: '最近活跃',
      dataIndex: 'lastSeenAt',
      align: 'right',
      width: 110,
      render: (value) => <Typography.Text type="secondary" className="text-xs">{formatRelativeTime(value)}</Typography.Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 72,
      align: 'right',
      fixed: 'right',
      render: (_, row) => <Button size="small" type="link" onClick={() => setSelected(row)}>查看</Button>,
    },
  ];

  return (
    <ApmRouteShell
      title="端点"
      description="按服务端点查看吞吐量、错误率与时延，通过查看操作打开详情与样本调用链。"
      dependency="telemetry"
    >
      <div className="flex flex-col gap-3">
        {metricFailureCount ? (
          <Alert
            action={<Button icon={<ReloadOutlined aria-hidden="true" />} size="small" onClick={load}>重试</Button>}
            description="已展示成功返回的服务，失败服务不会被误判为没有端点数据。"
            message={`部分服务的端点指标查询失败（${metricFailureCount} 项）`}
            showIcon
            type="warning"
          />
        ) : null}
        <ApmSurface padding="compact">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Input
              allowClear
              aria-label="搜索路径模板或服务"
              className="w-72"
              placeholder="搜索路径模板 / 服务"
              prefix={<SearchOutlined aria-hidden="true" />}
              value={keyword}
              onChange={(event) => { setKeyword(event.target.value); setPage(1); }}
            />
            <Select
              aria-label="环境"
              className="w-36"
              value={environment || undefined}
              placeholder="选择环境"
              options={environmentOptions}
              onChange={(value) => {
                setEnvironment(value);
                setServiceId('all');
                setPage(1);
              }}
            />
            <div className="flex-1" />
            <Select
              aria-label="服务"
              className="w-40"
              value={serviceId}
              options={[{ value: 'all', label: '全部服务' }, ...serviceOptions]}
              onChange={(value) => { setServiceId(value); setPage(1); }}
            />
            <Select<SortKey>
              aria-label="排序"
              className="w-32"
              value={sortKey}
              options={[
                { value: 'request_rate', label: '吞吐量' },
                { value: 'error_rate', label: '错误率' },
                { value: 'p95_ms', label: 'P95 耗时' },
              ]}
              onChange={(value) => { setSortKey(value); setPage(1); }}
            />
            <Radio.Group
              aria-label="时间范围"
              buttonStyle="solid"
              size="small"
              value={timeRange}
              onChange={(event) => setTimeRange(event.target.value)}
            >
              {(Object.keys(RANGE_MS) as MetricRange[]).map((value) => (
                <Radio.Button key={value} value={value}>{value}</Radio.Button>
              ))}
            </Radio.Group>
            <Button aria-label="刷新端点" icon={<ReloadOutlined aria-hidden="true" />} loading={state === 'loading'} onClick={load} />
          </FilterToolbar>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'ready' || (state === 'loading' && rows.length > 0) ? (
            <CustomTable
              autoScrollX={false}
              rowKey="key"
              size="middle"
              columns={columns}
              dataSource={pageRows}
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
            />
          ) : (
            <CatalogState
              kind={state}
              description={state === 'empty' ? '当前环境和时间范围内没有端点指标。' : undefined}
              onRetry={state === 'forbidden' ? undefined : load}
            />
          )}
        </ApmSurface>
      </div>
      <Drawer
        width="min(720px, 100vw)"
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
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {[
                { label: '吞吐', value: `${formatThroughput(selected.requestRate)}/s` },
                {
                  label: '错误率',
                  value: formatErrorRate(selected.errorRate),
                  danger: isErrorRateDanger(selected.errorRate),
                },
                { label: 'P95', value: formatLatency(selected.p95Ms) },
                { label: 'P99', value: formatLatency(selected.p99Ms) },
              ].map((metric) => (
                <SummaryMetricCard
                  key={metric.label}
                  className="rounded-lg px-3 py-2.5"
                  label={metric.label}
                  labelClassName="!text-xs"
                  layout="vertical"
                  maxFontSize={20}
                  minFontSize={18}
                  value={metric.value}
                  valueColor={metric.danger ? 'var(--color-fail)' : undefined}
                />
              ))}
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <Typography.Text strong>样本调用链</Typography.Text>
                <Link
                  href={`/apm/explore/traces?${new URLSearchParams({
                    service_namespace: selected.namespace,
                    service_name: selected.serviceName,
                    environment: selected.environment,
                  }).toString()}`}
                >
                  <Button type="link" size="small">在探索中打开</Button>
                </Link>
              </div>
              {samplesLoading ? (
                <CatalogState kind="loading" />
              ) : sampleTraces.length ? (
                <CustomTable
                  autoScrollX={false}
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
                      title: '资源',
                      dataIndex: 'root_span_name',
                      render: (value) => <span className="font-mono text-xs">{value}</span>,
                    },
                    {
                      title: '耗时',
                      dataIndex: 'duration_ms',
                      width: 90,
                      render: (value: number) => <span className="tabular-nums">{formatLatency(value)}</span>,
                    },
                    {
                      title: '时间',
                      dataIndex: 'started_at',
                      width: 100,
                      render: (value: string) => (
                        <span className="text-xs text-[var(--color-text-3)]">{formatRelativeTime(value)}</span>
                      ),
                    },
                  ]}
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配样本 Trace" />
              )}
            </div>
            <Typography.Text type="secondary" className="!text-xs">
              端点指标来自服务 RED Top endpoint 聚合；最近活跃参考服务发现时间 {dayjs(selected.lastSeenAt).format('YYYY-MM-DD HH:mm:ss')}。
            </Typography.Text>
          </div>
        ) : null}
      </Drawer>
    </ApmRouteShell>
  );
}
