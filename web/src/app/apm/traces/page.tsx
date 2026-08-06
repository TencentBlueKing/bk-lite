'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SearchOutlined } from '@ant-design/icons';
import { Button, Checkbox, Input, Segmented, Space, Table, Tag, Typography } from 'antd';
import type { TableProps } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import HealthDot from '@/app/apm/components/health-dot';
import { formatLatency, formatRelativeTime } from '@/app/apm/components/metric-format';
import type { ApmTraceSearchParams, ApmTraceSummary } from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready' | 'idle';
type TimeRange = '15m' | '1h' | '4h' | '1d' | '7d';
type ResultMode = 'detail' | 'aggregate';
type AggregateDimension = 'service' | 'endpoint' | 'status';

const RANGE_MS: Record<TimeRange, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

function TraceDistribution({ items }: { items: ApmTraceSummary[] }) {
  const width = 800;
  const height = 130;
  const sorted = [...items].sort((left, right) => left.started_at.localeCompare(right.started_at));
  const maxDuration = Math.max(...sorted.map((item) => item.duration_ms), 1);
  return (
    <svg
      aria-label={`Trace 耗时分布，共 ${items.length} 条`}
      className="block h-32 w-full"
      role="img"
      viewBox={`0 0 ${width} ${height}`}
    >
      {[0, 0.5, 1].map((ratio) => {
        const y = 10 + ratio * 100;
        return <line key={ratio} x1="0" x2={width} y1={y} y2={y} stroke="var(--color-border-1)" strokeDasharray="4 5" />;
      })}
      {sorted.map((item, index) => {
        const x = sorted.length === 1 ? width / 2 : 12 + (index / (sorted.length - 1)) * (width - 24);
        const y = 110 - (item.duration_ms / maxDuration) * 96;
        return (
          <circle
            aria-label={`${item.root_span_name}，${item.duration_ms.toFixed(2)} 毫秒`}
            cx={x}
            cy={y}
            fill={item.status === 'error' ? 'var(--color-fail)' : 'var(--color-primary)'}
            key={item.trace_id}
            r="5"
          />
        );
      })}
    </svg>
  );
}

interface AggregateRow {
  key: string;
  label: string;
  count: number;
  errorCount: number;
  errorRate: number;
  avgMs: number;
  p95Ms: number;
  maxMs: number;
}

function percentile(sorted: number[], ratio: number) {
  if (!sorted.length) return 0;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * ratio) - 1));
  return sorted[index];
}

function buildAggregate(items: ApmTraceSummary[], dimension: AggregateDimension): AggregateRow[] {
  const groups = new Map<string, ApmTraceSummary[]>();
  items.forEach((item) => {
    const key = dimension === 'service'
      ? item.service_name
      : dimension === 'endpoint'
        ? item.root_span_name || '(未命名)'
        : item.status;
    const list = groups.get(key) ?? [];
    list.push(item);
    groups.set(key, list);
  });
  return Array.from(groups.entries())
    .map(([key, group]) => {
      const durations = group.map((item) => item.duration_ms).sort((left, right) => left - right);
      const errorCount = group.filter((item) => item.status === 'error').length;
      return {
        key,
        label: dimension === 'status' ? (key === 'error' ? '错误' : '正常') : key,
        count: group.length,
        errorCount,
        errorRate: group.length ? errorCount / group.length : 0,
        avgMs: durations.reduce((total, value) => total + value, 0) / Math.max(group.length, 1),
        p95Ms: percentile(durations, 0.95),
        maxMs: durations[durations.length - 1] ?? 0,
      };
    })
    .sort((left, right) => right.count - left.count);
}

export default function ApmTracesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getTraces, isLoading: authLoading } = useApmApi();
  const [namespace, setNamespace] = useState(searchParams.get('service_namespace') ?? '');
  const [serviceName, setServiceName] = useState(searchParams.get('service_name') ?? '');
  const [environment, setEnvironment] = useState(searchParams.get('environment') ?? 'production');
  const [instanceId, setInstanceId] = useState(searchParams.get('instance_id') ?? '');
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [items, setItems] = useState<ApmTraceSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'ok' | 'error'>('all');
  const [serviceFilter, setServiceFilter] = useState<string>();
  const [resultMode, setResultMode] = useState<ResultMode>('detail');
  const [aggregateDimension, setAggregateDimension] = useState<AggregateDimension>('service');
  const [state, setState] = useState<PageState>(serviceName ? 'loading' : 'idle');
  const [queryStartedAt, setQueryStartedAt] = useState<string>();
  const [queryEndedAt, setQueryEndedAt] = useState<string>();
  const autoSearched = useRef(false);

  const buildQuery = useCallback((cursor?: string): ApmTraceSearchParams => {
    const linkedStart = searchParams.get('started_at');
    const linkedEnd = searchParams.get('ended_at');
    const endedAt = linkedEnd ?? new Date().toISOString();
    const startedAt = linkedStart ?? new Date(new Date(endedAt).getTime() - RANGE_MS[timeRange]).toISOString();
    return {
      service_namespace: namespace,
      service_name: serviceName,
      environment,
      instance_id: instanceId || undefined,
      started_at: startedAt,
      ended_at: endedAt,
      cursor,
      limit: 50,
    };
  }, [environment, instanceId, namespace, searchParams, serviceName, timeRange]);

  const search = useCallback((cursor?: string) => {
    if (!serviceName.trim() || authLoading) {
      setState('idle');
      return;
    }
    setState('loading');
    const query = buildQuery(cursor);
    getTraces(buildQuery(cursor))
      .then((page) => {
        setItems((current) => (cursor ? [...current, ...page.items] : page.items));
        setNextCursor(page.next_cursor);
        setQueryStartedAt(query.started_at);
        setQueryEndedAt(query.ended_at);
        setState(page.items.length === 0 && !cursor && !page.next_cursor ? 'empty' : 'ready');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [authLoading, buildQuery, getTraces, serviceName]);

  useEffect(() => {
    if (!authLoading && serviceName && !autoSearched.current) {
      autoSearched.current = true;
      search();
    }
  }, [authLoading, search, serviceName]);

  const columns = useMemo<TableProps<ApmTraceSummary>['columns']>(() => [
    {
      title: '入口服务 / Trace ID',
      render: (_, item) => (
        <Space direction="vertical" size={2}>
          <Space size={6}>
            <HealthDot level={item.status === 'error' ? 1 : 5} />
            <span className="text-[13px] font-medium">{item.service_name}</span>
          </Space>
          <span className="font-mono text-[11px] text-[var(--color-text-3)]">{item.trace_id}</span>
        </Space>
      ),
    },
    {
      title: '资源',
      dataIndex: 'root_span_name',
      render: (value) => <span className="font-mono text-xs">{value}</span>,
    },
    {
      title: '总耗时',
      dataIndex: 'duration_ms',
      width: 100,
      className: 'tabular-nums',
      render: (value: number) => formatLatency(value),
    },
    {
      title: '跨度数',
      dataIndex: 'span_count',
      width: 90,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['md'],
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value) => (
        value === 'error'
          ? <Tag bordered={false} color="error">错误</Tag>
          : <Tag bordered={false} color="success">正常</Tag>
      ),
    },
    {
      title: '时间',
      dataIndex: 'started_at',
      width: 110,
      responsive: ['lg'],
      render: (value: string) => (
        <span className="text-xs tabular-nums text-[var(--color-text-3)]">{formatRelativeTime(value)}</span>
      ),
    },
  ], []);

  const visibleItems = useMemo(
    () => items.filter((item) => (
      (statusFilter === 'all' || item.status === statusFilter)
      && (!serviceFilter || item.service_name === serviceFilter)
    )),
    [items, serviceFilter, statusFilter],
  );
  const statusCounts = useMemo(() => ({
    ok: items.filter((item) => item.status === 'ok').length,
    error: items.filter((item) => item.status === 'error').length,
  }), [items]);
  const serviceCounts = useMemo(() => Array.from(items.reduce((counts, item) => {
    counts.set(item.service_name, (counts.get(item.service_name) ?? 0) + 1);
    return counts;
  }, new Map<string, number>())).sort((left, right) => right[1] - left[1]), [items]);

  const windowSeconds = useMemo(() => {
    if (!queryStartedAt || !queryEndedAt) return RANGE_MS[timeRange] / 1000;
    return Math.max(1, (new Date(queryEndedAt).getTime() - new Date(queryStartedAt).getTime()) / 1000);
  }, [queryEndedAt, queryStartedAt, timeRange]);
  const hitRate = visibleItems.length / windowSeconds;
  const aggregateRows = useMemo(
    () => buildAggregate(visibleItems, aggregateDimension),
    [aggregateDimension, visibleItems]
  );

  const aggregateColumns: TableProps<AggregateRow>['columns'] = [
    {
      title: aggregateDimension === 'service' ? '服务' : aggregateDimension === 'endpoint' ? '端点 / 资源' : '状态',
      dataIndex: 'label',
      render: (value) => (
        aggregateDimension === 'endpoint'
          ? <span className="font-mono text-xs">{value}</span>
          : <span className="font-medium">{value}</span>
      ),
    },
    { title: '命中', dataIndex: 'count', width: 90, align: 'right', className: 'tabular-nums' },
    {
      title: '错误率',
      dataIndex: 'errorRate',
      width: 100,
      align: 'right',
      className: 'tabular-nums',
      render: (value: number) => (
        <span className={value >= 0.01 ? 'font-semibold text-[var(--color-fail)]' : undefined}>
          {(value * 100).toFixed(1)}%
        </span>
      ),
    },
    {
      title: '平均耗时',
      dataIndex: 'avgMs',
      width: 110,
      align: 'right',
      className: 'tabular-nums',
      render: (value: number) => formatLatency(value),
    },
    {
      title: 'P95',
      dataIndex: 'p95Ms',
      width: 100,
      align: 'right',
      className: 'tabular-nums',
      render: (value: number) => formatLatency(value),
    },
    {
      title: '最大耗时',
      dataIndex: 'maxMs',
      width: 100,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['lg'],
      render: (value: number) => formatLatency(value),
    },
  ];

  return (
    <ApmRouteShell
      title="调用链"
      description="按服务、环境与时间窗检索 Trace，支持明细列表与客户端聚合分析。"
      dependency="telemetry"
    >
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <Segmented
              aria-label="调用链查询粒度"
              options={[{ value: 'spans', label: 'Spans', disabled: true }, { value: 'traces', label: 'Traces' }]}
              value="traces"
            />
            <Typography.Text type="secondary" className="!text-xs">Spans 检索将在数据能力就绪后开放</Typography.Text>
            <div className="ml-auto">
              <Segmented<TimeRange>
                aria-label="时间窗"
                options={['15m', '1h', '4h', '1d', '7d']}
                size="small"
                value={timeRange}
                onChange={(value) => {
                  setTimeRange(value);
                  router.replace('/apm/traces');
                }}
              />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_1.3fr_auto]">
            <label className="min-w-0">
              <span className="mb-1 block text-xs font-medium text-[var(--color-text-2)]">应用 namespace</span>
              <Input value={namespace} onChange={(event) => setNamespace(event.target.value)} placeholder="可留空" />
            </label>
            <label className="min-w-0">
              <span className="mb-1 block text-xs font-medium text-[var(--color-text-2)]">服务名</span>
              <Input value={serviceName} onChange={(event) => setServiceName(event.target.value)} placeholder="必填" />
            </label>
            <label className="min-w-0">
              <span className="mb-1 block text-xs font-medium text-[var(--color-text-2)]">环境</span>
              <Input value={environment} onChange={(event) => setEnvironment(event.target.value)} placeholder="可留空" />
            </label>
            <label className="min-w-0">
              <span className="mb-1 block text-xs font-medium text-[var(--color-text-2)]">实例 ID</span>
              <Input value={instanceId} onChange={(event) => setInstanceId(event.target.value)} placeholder="可选" />
            </label>
            <div className="flex items-end">
              <Button
                type="primary"
                icon={<SearchOutlined aria-hidden="true" />}
                onClick={() => search()}
                disabled={!serviceName.trim()}
                block
              >
                搜索
              </Button>
            </div>
          </div>
        </ApmSurface>
        {state === 'idle' ? (
          <ApmSurface padding="none">
            <CatalogState kind="empty" description="输入服务名和环境后搜索 Trace。" />
          </ApmSurface>
        ) : state === 'ready' ? (
          <div className="grid min-h-0 grid-cols-1 gap-3 xl:grid-cols-[240px_minmax(0,1fr)]">
            <ApmSurface className="self-start" padding="compact">
              <Typography.Title level={2} className="!mb-4 !text-sm !font-semibold">分面筛选</Typography.Title>
              <div className="flex flex-col gap-5">
                <div>
                  <Typography.Text type="secondary" className="mb-2 block !text-xs">状态</Typography.Text>
                  <Space direction="vertical" size={6} className="w-full">
                    {([
                      { value: 'error' as const, label: '错误', count: statusCounts.error, color: 'var(--color-fail)' },
                      { value: 'ok' as const, label: '正常', count: statusCounts.ok, color: 'var(--color-success)' },
                    ]).map((item) => (
                      <div className="flex w-full items-center justify-between gap-3" key={item.value}>
                        <Checkbox
                          checked={statusFilter === item.value}
                          onChange={(event) => setStatusFilter(event.target.checked ? item.value : 'all')}
                        >
                          <span className="inline-flex items-center gap-1.5">
                            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full" style={{ background: item.color }} />
                            {item.label}
                          </span>
                        </Checkbox>
                        <span className="tabular-nums text-xs text-[var(--color-text-3)]">{item.count}</span>
                      </div>
                    ))}
                  </Space>
                </div>
                <div>
                  <Typography.Text type="secondary" className="mb-2 block !text-xs">服务</Typography.Text>
                  <Space direction="vertical" size={6} className="w-full">
                    {serviceCounts.slice(0, 8).map(([name, count]) => (
                      <button
                        key={name}
                        type="button"
                        className={`flex w-full items-center justify-between gap-3 rounded px-1 py-0.5 text-left hover:bg-[var(--color-fill-1)] ${
                          serviceFilter === name ? 'bg-[var(--color-primary-bg-active)]' : ''
                        }`}
                        onClick={() => setServiceFilter((current) => (current === name ? undefined : name))}
                      >
                        <Typography.Text ellipsis={{ tooltip: name }} className="max-w-36 !text-xs">{name}</Typography.Text>
                        <span className="tabular-nums text-xs text-[var(--color-text-3)]">{count}</span>
                      </button>
                    ))}
                  </Space>
                </div>
                <div>
                  <Typography.Text type="secondary" className="mb-2 block !text-xs">环境</Typography.Text>
                  <Tag bordered={false}>{environment || '未设置'}</Tag>
                </div>
              </div>
            </ApmSurface>
            <div className="flex min-w-0 flex-col gap-3">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <div className="flex items-baseline gap-2">
                    <strong className="text-2xl tabular-nums">{hitRate >= 10 ? hitRate.toFixed(1) : hitRate.toFixed(2)}</strong>
                    <Typography.Text type="secondary" className="!text-xs">traces/s</Typography.Text>
                  </div>
                  <Typography.Text type="secondary" className="!text-xs">
                    命中 {visibleItems.length} 条 · 窗 {timeRange}
                  </Typography.Text>
                </div>
                <Segmented<ResultMode>
                  options={[
                    { value: 'detail', label: '明细' },
                    { value: 'aggregate', label: '聚合' },
                  ]}
                  value={resultMode}
                  onChange={setResultMode}
                />
              </div>
              {resultMode === 'detail' ? (
                <>
                  <ApmSurface padding="compact">
                    <div className="mb-1 flex items-center justify-between">
                      <Typography.Text strong>耗时分布</Typography.Text>
                      <Space size={12}>
                        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-text-3)]"><span className="h-1.5 w-1.5 rounded-full bg-[var(--color-primary)]" />正常</span>
                        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-text-3)]"><span className="h-1.5 w-1.5 rounded-full bg-[var(--color-fail)]" />错误</span>
                      </Space>
                    </div>
                    <TraceDistribution items={visibleItems} />
                  </ApmSurface>
                  <ApmSurface padding="none" className="overflow-hidden">
                    <Table
                      size="middle"
                      rowKey="trace_id"
                      columns={columns}
                      dataSource={visibleItems}
                      pagination={false}
                      onRow={(item) => ({
                        onClick: () => router.push(`/apm/traces/${item.trace_id}`),
                        onKeyDown: (event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            router.push(`/apm/traces/${item.trace_id}`);
                          }
                        },
                        role: 'link',
                        'aria-label': `查看 Trace ${item.trace_id}`,
                        tabIndex: 0,
                        className: 'cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)] focus-visible:outline-offset-[-2px]',
                      })}
                    />
                    {nextCursor ? (
                      <div className="flex justify-center border-t border-[var(--color-border-1)] p-3">
                        <Button onClick={() => search(nextCursor)}>加载更多</Button>
                      </div>
                    ) : null}
                  </ApmSurface>
                </>
              ) : (
                <ApmSurface padding="none" className="overflow-hidden">
                  <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
                    <Typography.Text strong>聚合分析</Typography.Text>
                    <Segmented<AggregateDimension>
                      size="small"
                      value={aggregateDimension}
                      onChange={setAggregateDimension}
                      options={[
                        { value: 'service', label: '按服务' },
                        { value: 'endpoint', label: '按端点' },
                        { value: 'status', label: '按状态' },
                      ]}
                    />
                  </div>
                  <Table
                    size="middle"
                    rowKey="key"
                    columns={aggregateColumns}
                    dataSource={aggregateRows}
                    pagination={false}
                  />
                </ApmSurface>
              )}
            </div>
          </div>
        ) : (
          <ApmSurface padding="none">
            <CatalogState kind={state} description={state === 'empty' ? '当前条件下没有可见 Trace。' : undefined} />
          </ApmSurface>
        )}
      </div>
    </ApmRouteShell>
  );
}
