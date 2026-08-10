'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SearchOutlined } from '@ant-design/icons';
import { Button, Checkbox, Input, InputNumber, Segmented, Select, Space, Table, Tag, Typography } from 'antd';
import type { TableProps } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import HealthDot from '@/app/apm/components/health-dot';
import { formatLatency, formatRelativeTime } from '@/app/apm/components/metric-format';
import type {
  ApmSpanSearchParams,
  ApmSpanSummary,
  ApmTraceSearchParams,
  ApmTraceSummary,
} from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';

type PageState = CatalogStateKind | 'ready' | 'idle';
type TimeRange = '15m' | '1h' | '4h' | '1d' | '7d';
type ResultMode = 'detail' | 'aggregate';
type AggregateDimension = 'service' | 'endpoint' | 'status';
type EntityMode = 'spans' | 'traces';
type SpanKind = 'internal' | 'server' | 'client' | 'producer' | 'consumer';

const RANGE_MS: Record<TimeRange, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
};

const SPAN_KINDS: SpanKind[] = ['internal', 'server', 'client', 'producer', 'consumer'];

interface TraceFilters {
  namespace: string;
  serviceName: string;
  environment: string;
  instanceId: string;
  spanName: string;
  status: 'all' | 'ok' | 'error';
  kind?: SpanKind;
  minDurationMs: number | null;
  maxDurationMs: number | null;
}

function serializeFilters(filters: TraceFilters): string {
  const tokens: string[] = [];
  if (filters.namespace.trim()) tokens.push(`service_namespace:${filters.namespace.trim()}`);
  if (filters.serviceName.trim()) tokens.push(`service:${filters.serviceName.trim()}`);
  if (filters.environment.trim()) tokens.push(`environment:${filters.environment.trim()}`);
  if (filters.instanceId.trim()) tokens.push(`instance:${filters.instanceId.trim()}`);
  if (filters.spanName.trim()) tokens.push(`name:${filters.spanName.trim()}`);
  if (filters.status !== 'all') tokens.push(`status:${filters.status}`);
  if (filters.kind) tokens.push(`kind:${filters.kind}`);
  if (filters.minDurationMs != null) tokens.push(`duration:>=${filters.minDurationMs}ms`);
  if (filters.maxDurationMs != null) tokens.push(`duration:<=${filters.maxDurationMs}ms`);
  return tokens.join(' ');
}

function parseDurationToken(raw: string): { op: 'min' | 'max'; value: number } | null {
  const match = raw.trim().match(/^(>=|<=|>|<)?\s*(\d+(?:\.\d+)?)\s*ms$/i);
  if (!match) return null;
  const op = match[1] || '>=';
  const value = Number(match[2]);
  if (!Number.isFinite(value) || value < 0) return null;
  if (op === '>' || op === '>=') return { op: 'min', value };
  return { op: 'max', value };
}

function parseFilters(text: string, fallback: TraceFilters): TraceFilters {
  const next: TraceFilters = {
    namespace: '',
    serviceName: '',
    environment: '',
    instanceId: '',
    spanName: '',
    status: 'all',
    kind: undefined,
    minDurationMs: null,
    maxDurationMs: null,
  };
  const tokens: string[] = text.match(/(?:[^\s"]+|"[^"]*")+/g) ?? [];
  tokens.forEach((token) => {
    const cleaned = token.replace(/^"|"$/g, '');
    const sep = cleaned.indexOf(':');
    if (sep <= 0) return;
    const key = cleaned.slice(0, sep).trim().toLocaleLowerCase();
    const value = cleaned.slice(sep + 1).trim();
    if (!value) return;
    if (key === 'service' || key === 'service_name') next.serviceName = value;
    else if (key === 'service_namespace' || key === 'namespace') next.namespace = value;
    else if (key === 'environment' || key === 'env') next.environment = value;
    else if (key === 'instance' || key === 'instance_id') next.instanceId = value;
    else if (key === 'name' || key === 'operation' || key === 'resource' || key === 'span_name') next.spanName = value;
    else if (key === 'status' && (value === 'ok' || value === 'error')) next.status = value;
    else if (key === 'kind' && SPAN_KINDS.includes(value as SpanKind)) next.kind = value as SpanKind;
    else if (key === 'duration') {
      const parsed = parseDurationToken(value);
      if (!parsed) return;
      if (parsed.op === 'min') next.minDurationMs = parsed.value;
      else next.maxDurationMs = parsed.value;
    }
  });
  if (!next.serviceName && fallback.serviceName) next.serviceName = fallback.serviceName;
  if (!next.environment && fallback.environment) next.environment = fallback.environment;
  return next;
}

function filtersFromSearchParams(params: URLSearchParams): TraceFilters {
  const kind = params.get('kind');
  return {
    namespace: params.get('service_namespace') ?? '',
    serviceName: params.get('service_name') ?? '',
    environment: params.get('environment') ?? '',
    instanceId: params.get('instance_id') ?? '',
    spanName: params.get('span_name') ?? '',
    status: params.get('status') === 'ok' || params.get('status') === 'error'
      ? params.get('status') as 'ok' | 'error'
      : 'all',
    kind: SPAN_KINDS.includes(kind as SpanKind) ? kind as SpanKind : undefined,
    minDurationMs: params.get('min_duration_ms') ? Number(params.get('min_duration_ms')) : null,
    maxDurationMs: params.get('max_duration_ms') ? Number(params.get('max_duration_ms')) : null,
  };
}

interface DurationPoint {
  key: string;
  started_at: string;
  duration_ms: number;
  status: 'ok' | 'error';
  label: string;
}

function TraceDistribution({ items, unitLabel }: { items: DurationPoint[]; unitLabel: string }) {
  return <DurationDistribution items={items} unitLabel={unitLabel} />;
}

function DurationDistribution({ items, unitLabel }: { items: DurationPoint[]; unitLabel: string }) {
  const width = 800;
  const height = 130;
  const sorted = [...items].sort((left, right) => left.started_at.localeCompare(right.started_at));
  const maxDuration = Math.max(...sorted.map((item) => item.duration_ms), 1);
  return (
    <svg
      aria-label={`${unitLabel} 耗时分布，共 ${items.length} 条`}
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
            aria-label={`${item.label}，${item.duration_ms.toFixed(2)} 毫秒`}
            cx={x}
            cy={y}
            fill={item.status === 'error' ? 'var(--color-fail)' : 'var(--color-primary)'}
            key={item.key}
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

function buildAggregate(
  items: Array<{ service_name: string; status: string; duration_ms: number; endpoint: string }>,
  dimension: AggregateDimension,
): AggregateRow[] {
  const groups = new Map<string, typeof items>();
  items.forEach((item) => {
    const key = dimension === 'service'
      ? item.service_name
      : dimension === 'endpoint'
        ? item.endpoint || '(未命名)'
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
  const { getSpans, getTraces, isLoading: authLoading } = useApmApi();
  const initialFilters = useMemo(() => filtersFromSearchParams(searchParams), [searchParams]);
  const [entityMode, setEntityMode] = useState<EntityMode>(
    searchParams.get('entity') === 'traces' ? 'traces' : 'spans',
  );
  const [filters, setFilters] = useState<TraceFilters>(initialFilters);
  const [queryText, setQueryText] = useState(() => serializeFilters(initialFilters));
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [traceItems, setTraceItems] = useState<ApmTraceSummary[]>([]);
  const [spanItems, setSpanItems] = useState<ApmSpanSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [serviceFilter, setServiceFilter] = useState<string>();
  const [resultMode, setResultMode] = useState<ResultMode>('detail');
  const [aggregateDimension, setAggregateDimension] = useState<AggregateDimension>('service');
  const [state, setState] = useState<PageState>(initialFilters.serviceName ? 'loading' : 'idle');
  const [queryStartedAt, setQueryStartedAt] = useState<string>();
  const [queryEndedAt, setQueryEndedAt] = useState<string>();
  const autoSearched = useRef(false);
  const entityModeReady = useRef(false);

  const {
    namespace,
    serviceName,
    environment,
    instanceId,
    spanName,
    status: queryStatus,
    kind,
    minDurationMs,
    maxDurationMs,
  } = filters;

  const applyFilters = useCallback((next: TraceFilters, options?: { search?: boolean }) => {
    setFilters(next);
    setQueryText(serializeFilters(next));
    if (options?.search === false) return;
  }, []);

  const timeWindow = useCallback((cursor?: string) => {
    const linkedStart = searchParams.get('started_at');
    const linkedEnd = searchParams.get('ended_at');
    const endedAt = linkedEnd ?? new Date().toISOString();
    const startedAt = linkedStart ?? new Date(new Date(endedAt).getTime() - RANGE_MS[timeRange]).toISOString();
    return { started_at: startedAt, ended_at: endedAt, cursor };
  }, [searchParams, timeRange]);

  const search = useCallback((cursor?: string, nextFilters?: TraceFilters) => {
    const active = nextFilters ?? filters;
    if (!active.serviceName.trim() || authLoading) {
      setState('idle');
      return;
    }
    setState('loading');
    const window = timeWindow(cursor);
    if (entityMode === 'spans') {
      const query: ApmSpanSearchParams = {
        service_namespace: active.namespace || undefined,
        service_name: active.serviceName,
        environment: active.environment,
        instance_id: active.instanceId || undefined,
        span_name: active.spanName || undefined,
        status: active.status === 'all' ? undefined : active.status,
        kind: active.kind,
        min_duration_ms: active.minDurationMs ?? undefined,
        max_duration_ms: active.maxDurationMs ?? undefined,
        ...window,
        limit: 50,
      };
      getSpans(query)
        .then((page) => {
          setSpanItems((current) => (cursor ? [...current, ...page.items] : page.items));
          setTraceItems([]);
          setNextCursor(page.next_cursor);
          setQueryStartedAt(query.started_at);
          setQueryEndedAt(query.ended_at);
          setState(page.items.length === 0 && !cursor && !page.next_cursor ? 'empty' : 'ready');
        })
        .catch((error) => setState(catalogErrorKind(error)));
      return;
    }
    const query: ApmTraceSearchParams = {
      service_namespace: active.namespace || undefined,
      service_name: active.serviceName,
      environment: active.environment,
      instance_id: active.instanceId || undefined,
      span_name: active.spanName || undefined,
      status: active.status === 'all' ? undefined : active.status,
      min_duration_ms: active.minDurationMs ?? undefined,
      max_duration_ms: active.maxDurationMs ?? undefined,
      ...window,
      limit: 50,
    };
    getTraces(query)
      .then((page) => {
        setTraceItems((current) => (cursor ? [...current, ...page.items] : page.items));
        setSpanItems([]);
        setNextCursor(page.next_cursor);
        setQueryStartedAt(query.started_at);
        setQueryEndedAt(query.ended_at);
        setState(page.items.length === 0 && !cursor && !page.next_cursor ? 'empty' : 'ready');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [authLoading, entityMode, filters, getSpans, getTraces, timeWindow]);

  const commitQueryText = useCallback(() => {
    const next = parseFilters(queryText, filters);
    applyFilters(next);
    search(undefined, next);
  }, [applyFilters, filters, queryText, search]);

  const patchFilters = useCallback((patch: Partial<TraceFilters>) => {
    const next = { ...filters, ...patch };
    applyFilters(next);
    search(undefined, next);
  }, [applyFilters, filters, search]);

  useEffect(() => {
    if (!authLoading && serviceName && !autoSearched.current) {
      autoSearched.current = true;
      entityModeReady.current = true;
      search();
    }
  }, [authLoading, search, serviceName]);

  useEffect(() => {
    if (!entityModeReady.current || authLoading || !serviceName.trim()) return;
    search();
  }, [entityMode]); // eslint-disable-line react-hooks/exhaustive-deps -- 仅在切换 Spans/Traces 时重查

  useEffect(() => {
    if (!autoSearched.current || authLoading || !serviceName.trim()) return;
    search();
  }, [timeRange]); // eslint-disable-line react-hooks/exhaustive-deps -- 时间窗变更后按新窗重查

  const traceColumns = useMemo<TableProps<ApmTraceSummary>['columns']>(() => [
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

  const spanColumns = useMemo<TableProps<ApmSpanSummary>['columns']>(() => [
    {
      title: '服务',
      render: (_, item) => (
        <Space size={6}>
          <HealthDot level={item.status === 'error' ? 1 : 5} />
          <span className="text-[13px] font-medium">{item.service_name}</span>
        </Space>
      ),
    },
    {
      title: '资源',
      dataIndex: 'name',
      render: (value) => <span className="font-mono text-xs">{value}</span>,
    },
    {
      title: 'HTTP',
      width: 120,
      render: (_, item) => {
        if (!item.http_method && !item.http_status_code) {
          return <span className="text-xs text-[var(--color-text-3)]">-</span>;
        }
        return (
          <span className="font-mono text-xs">
            {[item.http_method, item.http_status_code].filter(Boolean).join(' ')}
          </span>
        );
      },
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 100,
      className: 'tabular-nums',
      render: (value: number) => formatLatency(value),
    },
    {
      title: '时间',
      dataIndex: 'started_at',
      width: 110,
      render: (value: string) => (
        <span className="text-xs tabular-nums text-[var(--color-text-3)]">{formatRelativeTime(value)}</span>
      ),
    },
  ], []);

  const visibleTraces = useMemo(
    () => traceItems.filter((item) => (!serviceFilter || item.service_name === serviceFilter)),
    [serviceFilter, traceItems],
  );
  const visibleSpans = useMemo(
    () => spanItems.filter((item) => (!serviceFilter || item.service_name === serviceFilter)),
    [serviceFilter, spanItems],
  );
  const activeItems = entityMode === 'spans' ? visibleSpans : visibleTraces;
  const statusCounts = useMemo(() => {
    const source = entityMode === 'spans' ? spanItems : traceItems;
    return {
      ok: source.filter((item) => item.status === 'ok').length,
      error: source.filter((item) => item.status === 'error').length,
    };
  }, [entityMode, spanItems, traceItems]);
  const serviceCounts = useMemo(() => {
    const source = entityMode === 'spans' ? spanItems : traceItems;
    return Array.from(source.reduce((counts, item) => {
      counts.set(item.service_name, (counts.get(item.service_name) ?? 0) + 1);
      return counts;
    }, new Map<string, number>())).sort((left, right) => right[1] - left[1]);
  }, [entityMode, spanItems, traceItems]);
  const environmentCounts = useMemo(() => {
    const source = entityMode === 'spans' ? spanItems : traceItems;
    return Array.from(source.reduce((counts, item) => {
      const key = item.environment || '(未设置)';
      counts.set(key, (counts.get(key) ?? 0) + 1);
      return counts;
    }, new Map<string, number>())).sort((left, right) => right[1] - left[1]);
  }, [entityMode, spanItems, traceItems]);
  const kindCounts = useMemo(() => {
    if (entityMode !== 'spans') return [] as Array<[string, number]>;
    return Array.from(spanItems.reduce((counts, item) => {
      const key = item.kind || 'unspecified';
      counts.set(key, (counts.get(key) ?? 0) + 1);
      return counts;
    }, new Map<string, number>())).sort((left, right) => right[1] - left[1]);
  }, [entityMode, spanItems]);

  const windowSeconds = useMemo(() => {
    if (!queryStartedAt || !queryEndedAt) return RANGE_MS[timeRange] / 1000;
    return Math.max(1, (new Date(queryEndedAt).getTime() - new Date(queryStartedAt).getTime()) / 1000);
  }, [queryEndedAt, queryStartedAt, timeRange]);
  const hitRate = activeItems.length / windowSeconds;
  const distributionItems = useMemo<DurationPoint[]>(
    () => (entityMode === 'spans'
      ? visibleSpans.map((item) => ({
        key: item.span_id,
        started_at: item.started_at,
        duration_ms: item.duration_ms,
        status: item.status,
        label: item.name,
      }))
      : visibleTraces.map((item) => ({
        key: item.trace_id,
        started_at: item.started_at,
        duration_ms: item.duration_ms,
        status: item.status,
        label: item.root_span_name,
      }))),
    [entityMode, visibleSpans, visibleTraces],
  );
  const aggregateRows = useMemo(
    () => buildAggregate(
      entityMode === 'spans'
        ? visibleSpans.map((item) => ({
          service_name: item.service_name,
          status: item.status,
          duration_ms: item.duration_ms,
          endpoint: item.name,
        }))
        : visibleTraces.map((item) => ({
          service_name: item.service_name,
          status: item.status,
          duration_ms: item.duration_ms,
          endpoint: item.root_span_name,
        })),
      aggregateDimension,
    ),
    [aggregateDimension, entityMode, visibleSpans, visibleTraces],
  );

  const aggregateColumns: TableProps<AggregateRow>['columns'] = [
    { title: '分组', dataIndex: 'label' },
    { title: '数量', dataIndex: 'count', width: 90, align: 'right', className: 'tabular-nums' },
    {
      title: '错误率',
      dataIndex: 'errorRate',
      width: 100,
      align: 'right',
      className: 'tabular-nums',
      render: (value: number) => `${(value * 100).toFixed(1)}%`,
    },
    {
      title: '平均耗时',
      dataIndex: 'avgMs',
      width: 100,
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
      description="按服务、环境与时间窗检索 Trace 或 Span，支持明细列表与客户端聚合分析。"
      dependency="telemetry"
    >
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Segmented<EntityMode>
              size="small"
              aria-label="调用链查询粒度"
              options={[
                { value: 'spans', label: 'Spans' },
                { value: 'traces', label: 'Traces' },
              ]}
              value={entityMode}
              onChange={(value) => {
                if (value !== 'spans' && value !== 'traces') return;
                setEntityMode(value);
                setResultMode('detail');
                setNextCursor(null);
                setTraceItems([]);
                setSpanItems([]);
                setState(serviceName.trim() ? 'loading' : 'idle');
              }}
            />
            <Input
              allowClear
              aria-label="调用链过滤条件"
              className="min-w-[280px] flex-1"
              placeholder="按 key:value 过滤，如 service:auth environment:lab status:error duration:>=30ms"
              prefix={<SearchOutlined className="text-[var(--color-text-3)]" aria-hidden="true" />}
              value={queryText}
              onChange={(event) => setQueryText(event.target.value)}
              onPressEnter={commitQueryText}
              onClear={() => {
                const cleared: TraceFilters = {
                  namespace: '',
                  serviceName: '',
                  environment: '',
                  instanceId: '',
                  spanName: '',
                  status: 'all',
                  kind: undefined,
                  minDurationMs: null,
                  maxDurationMs: null,
                };
                applyFilters(cleared);
                setState('idle');
                setTraceItems([]);
                setSpanItems([]);
              }}
            />
            <Space size={4}>
              <Select
                size="small"
                aria-label="时间窗"
                className="w-[90px]"
                value={timeRange}
                options={['15m', '1h', '4h', '1d', '7d'].map((value) => ({ value, label: value }))}
                onChange={(value: TimeRange) => {
                  setTimeRange(value);
                  router.replace(`/apm/explore/traces${entityMode === 'spans' ? '?entity=spans' : '?entity=traces'}`);
                }}
              />
              <Select
                size="small"
                aria-label="实时尾随"
                className="w-[88px]"
                disabled
                value="off"
                title="实时尾随尚未开放"
                options={[{ value: 'off', label: 'off' }]}
              />
            </Space>
          </FilterToolbar>
        </ApmSurface>
        {state === 'idle' ? (
          <ApmSurface padding="none">
            <CatalogState kind="empty" description="在上方输入 service:... 后回车搜索调用链。" />
          </ApmSurface>
        ) : state === 'ready' ? (
          <div className="grid min-h-0 grid-cols-1 gap-3 xl:grid-cols-[240px_minmax(0,1fr)]">
            <ApmSurface className="self-start" padding="compact">
              <Typography.Title level={2} className="!mb-4 !text-sm !font-semibold">分面筛选</Typography.Title>
              <div className="flex flex-col gap-5">
                <div>
                  <Typography.Text type="secondary" className="mb-2 block !text-xs">
                    状态
                    {queryStatus !== 'all' ? (
                      <span className="ml-1.5 font-semibold text-[var(--color-primary)]">(1)</span>
                    ) : null}
                  </Typography.Text>
                  <Space direction="vertical" size={6} className="w-full">
                    {([
                      { value: 'error' as const, label: '错误', count: statusCounts.error, color: 'var(--color-fail)' },
                      { value: 'ok' as const, label: '正常', count: statusCounts.ok, color: 'var(--color-success)' },
                    ]).map((item) => (
                      <div
                        key={item.value}
                        className={`flex w-full items-center justify-between gap-3 rounded px-1.5 py-0.5 ${
                          queryStatus === item.value ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]' : ''
                        }`}
                      >
                        <Checkbox
                          checked={queryStatus === item.value}
                          onChange={(event) => patchFilters({
                            status: event.target.checked ? item.value : 'all',
                          })}
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
                  <Typography.Text type="secondary" className="mb-2 block !text-xs">
                    服务
                    {serviceFilter ? (
                      <span className="ml-1.5 font-semibold text-[var(--color-primary)]">(1)</span>
                    ) : null}
                  </Typography.Text>
                  <Space direction="vertical" size={6} className="w-full">
                    {serviceCounts.slice(0, 8).map(([name, count]) => (
                      <button
                        key={name}
                        type="button"
                        className={`flex w-full items-center justify-between gap-3 rounded px-1.5 py-0.5 text-left hover:bg-[var(--color-fill-1)] ${
                          serviceFilter === name ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]' : ''
                        }`}
                        onClick={() => setServiceFilter((current) => (current === name ? undefined : name))}
                      >
                        <Typography.Text ellipsis={{ tooltip: name }} className="max-w-36 !text-xs !text-inherit">{name}</Typography.Text>
                        <span className="tabular-nums text-xs text-[var(--color-text-3)]">{count}</span>
                      </button>
                    ))}
                  </Space>
                </div>
                <div>
                  <Typography.Text type="secondary" className="mb-2 block !text-xs">
                    环境
                    {environment ? (
                      <span className="ml-1.5 font-semibold text-[var(--color-primary)]">(1)</span>
                    ) : null}
                  </Typography.Text>
                  <Space direction="vertical" size={6} className="w-full">
                    {(environmentCounts.length ? environmentCounts : [[environment || '(未设置)', 0] as [string, number]]).slice(0, 8).map(([name, count]) => (
                      <button
                        key={name}
                        type="button"
                        className={`flex w-full items-center justify-between gap-3 rounded px-1.5 py-0.5 text-left hover:bg-[var(--color-fill-1)] ${
                          (environment || '(未设置)') === name ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]' : ''
                        }`}
                        onClick={() => patchFilters({
                          environment: name === '(未设置)' ? '' : name,
                        })}
                      >
                        <Typography.Text ellipsis={{ tooltip: name }} className="max-w-36 !text-xs !text-inherit">{name}</Typography.Text>
                        <span className="tabular-nums text-xs text-[var(--color-text-3)]">{count}</span>
                      </button>
                    ))}
                  </Space>
                </div>
                {entityMode === 'spans' ? (
                  <div>
                    <Typography.Text type="secondary" className="mb-2 block !text-xs">
                      SPAN 类型
                      {kind ? (
                        <span className="ml-1.5 font-semibold text-[var(--color-primary)]">(1)</span>
                      ) : null}
                    </Typography.Text>
                    <Space direction="vertical" size={6} className="w-full">
                      {(kindCounts.length
                        ? kindCounts
                        : SPAN_KINDS.map((value) => [value, 0] as [string, number])
                      ).map(([name, count]) => (
                        <div
                          key={name}
                          className={`flex w-full items-center justify-between gap-3 rounded px-1.5 py-0.5 ${
                            kind === name ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]' : ''
                          }`}
                        >
                          <Checkbox
                            checked={kind === name}
                            onChange={(event) => patchFilters({
                              kind: event.target.checked && SPAN_KINDS.includes(name as SpanKind)
                                ? name as SpanKind
                                : undefined,
                            })}
                          >
                            <span className="text-xs uppercase">{name}</span>
                          </Checkbox>
                          <span className="tabular-nums text-xs text-[var(--color-text-3)]">{count}</span>
                        </div>
                      ))}
                    </Space>
                  </div>
                ) : null}
                <div>
                  <Typography.Text type="secondary" className="mb-2 block !text-xs">耗时</Typography.Text>
                  <div className="mt-2 flex items-center gap-1.5">
                    <InputNumber
                      size="small"
                      min={0}
                      className="w-full"
                      placeholder="min"
                      value={minDurationMs}
                      onChange={(value) => applyFilters({
                        ...filters,
                        minDurationMs: typeof value === 'number' ? value : null,
                      }, { search: false })}
                    />
                    <span className="text-xs text-[var(--color-text-3)]">-</span>
                    <InputNumber
                      size="small"
                      min={0}
                      className="w-full"
                      placeholder="max"
                      value={maxDurationMs}
                      onChange={(value) => applyFilters({
                        ...filters,
                        maxDurationMs: typeof value === 'number' ? value : null,
                      }, { search: false })}
                    />
                    <span className="shrink-0 text-xs text-[var(--color-text-3)]">ms</span>
                  </div>
                  <Button
                    size="small"
                    className="mt-2"
                    onClick={() => search(undefined, filters)}
                  >
                    应用耗时
                  </Button>
                </div>
              </div>
            </ApmSurface>
            <div className="flex min-w-0 flex-col gap-3">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <div className="flex items-baseline gap-2">
                    <strong className="text-2xl tabular-nums">{hitRate >= 10 ? hitRate.toFixed(1) : hitRate.toFixed(2)}</strong>
                    <Typography.Text type="secondary" className="!text-xs">
                      {entityMode === 'spans' ? 'spans/s' : 'traces/s'}
                    </Typography.Text>
                  </div>
                  <Typography.Text type="secondary" className="!text-xs">
                    命中 {activeItems.length} 条 · 窗 {timeRange}
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
                    <TraceDistribution
                      items={distributionItems}
                      unitLabel={entityMode === 'spans' ? 'Span' : 'Trace'}
                    />
                  </ApmSurface>
                  <ApmSurface padding="none" className="overflow-hidden">
                    {entityMode === 'spans' ? (
                      <Table
                        size="middle"
                        rowKey="span_id"
                        columns={spanColumns}
                        dataSource={visibleSpans}
                        pagination={false}
                        onRow={(item) => ({
                          onClick: () => router.push(`/apm/explore/traces/${item.trace_id}?span_id=${item.span_id}`),
                          onKeyDown: (event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              router.push(`/apm/explore/traces/${item.trace_id}?span_id=${item.span_id}`);
                            }
                          },
                          role: 'link',
                          'aria-label': `查看 Span ${item.span_id}`,
                          tabIndex: 0,
                          className: 'cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)] focus-visible:outline-offset-[-2px]',
                        })}
                      />
                    ) : (
                      <Table
                        size="middle"
                        rowKey="trace_id"
                        columns={traceColumns}
                        dataSource={visibleTraces}
                        pagination={false}
                        onRow={(item) => ({
                          onClick: () => router.push(`/apm/explore/traces/${item.trace_id}`),
                          onKeyDown: (event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              router.push(`/apm/explore/traces/${item.trace_id}`);
                            }
                          },
                          role: 'link',
                          'aria-label': `查看 Trace ${item.trace_id}`,
                          tabIndex: 0,
                          className: 'cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)] focus-visible:outline-offset-[-2px]',
                        })}
                      />
                    )}
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
            <CatalogState
              kind={state}
              description={state === 'empty'
                ? (entityMode === 'spans' ? '当前条件下没有可见 Span。' : '当前条件下没有可见 Trace。')
                : undefined}
            />
          </ApmSurface>
        )}
      </div>
    </ApmRouteShell>
  );
}
