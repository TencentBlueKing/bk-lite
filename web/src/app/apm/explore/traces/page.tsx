'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { SearchOutlined } from '@ant-design/icons';
import { Button, Checkbox, Input, InputNumber, Segmented, Select, Space, Tag, Typography } from 'antd';
import type { TableProps } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import HealthDot from '@/app/apm/components/health-dot';
import {
  formatCompactLatency,
  formatDateTime,
  formatErrorRate,
  formatLatency,
  formatNumber,
  formatRelativeTime,
} from '@/app/apm/components/metric-format';
import type {
  ApmService,
  ApmSpanSearchParams,
  ApmSpanSummary,
  ApmTraceSearchParams,
  ApmTraceSummary,
} from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';
import { useTranslation } from '@/utils/i18n';

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

interface ResultFacets {
  status: 'all' | 'ok' | 'error';
  serviceName?: string;
  environment?: string;
  kind?: string;
  minDurationMs: number | null;
  maxDurationMs: number | null;
}

const EMPTY_RESULT_FACETS: ResultFacets = {
  status: 'all',
  minDurationMs: null,
  maxDurationMs: null,
};

function parseSpanKind(value: string | null | undefined): SpanKind | undefined {
  const normalized = (value ?? '').trim().toLowerCase();
  return SPAN_KINDS.includes(normalized as SpanKind) ? normalized as SpanKind : undefined;
}

function normalizeSpanKind(value: string | undefined): string {
  return (value ?? '').trim().toLowerCase();
}

function matchesResultFacets(
  item: {
    status: string;
    service_name: string;
    environment?: string | null;
    kind?: string;
    duration_ms: number;
  },
  facets: ResultFacets,
): boolean {
  if (facets.status !== 'all' && item.status !== facets.status) return false;
  if (facets.serviceName && item.service_name !== facets.serviceName) return false;
  if (facets.environment !== undefined && (item.environment || '') !== facets.environment) return false;
  if (facets.kind && normalizeSpanKind(item.kind) !== facets.kind) return false;
  if (facets.minDurationMs != null && item.duration_ms < facets.minDurationMs) return false;
  if (facets.maxDurationMs != null && item.duration_ms > facets.maxDurationMs) return false;
  return true;
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

function parseDurationInput(value: number | string | null): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
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

function parseFilters(text: string): TraceFilters {
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
    else if (key === 'kind') {
      const parsed = parseSpanKind(value);
      if (parsed) next.kind = parsed;
    }
    else if (key === 'duration') {
      const parsed = parseDurationToken(value);
      if (!parsed) return;
      if (parsed.op === 'min') next.minDurationMs = parsed.value;
      else next.maxDurationMs = parsed.value;
    }
  });
  return next;
}

function filtersFromSearchParams(params: URLSearchParams): TraceFilters {
  return {
    namespace: params.get('service_namespace') ?? '',
    serviceName: params.get('service_name') ?? '',
    environment: params.get('environment') ?? '',
    instanceId: params.get('instance_id') ?? '',
    spanName: params.get('span_name') ?? '',
    status: params.get('status') === 'ok' || params.get('status') === 'error'
      ? params.get('status') as 'ok' | 'error'
      : 'all',
    kind: parseSpanKind(params.get('kind')),
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

function useContainerWidth(defaultWidth = 1000) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(defaultWidth);

  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect && entry.contentRect.width > 0) {
          setWidth(Math.round(entry.contentRect.width));
        }
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return { ref, width };
}

function DurationDistribution({ items, unitLabel }: { items: DurationPoint[]; unitLabel: string }) {
  const { t } = useTranslation();
  const { ref, width } = useContainerWidth(1000);
  const height = 130;
  const sorted = [...items].sort((left, right) => left.started_at.localeCompare(right.started_at));
  const maxDuration = Math.max(...sorted.map((item) => item.duration_ms), 1);
  const maxLabel = formatCompactLatency(maxDuration);
  const midLabel = formatCompactLatency(maxDuration / 2);

  const leftMargin = 52;
  const rightMargin = 20;
  const chartWidth = Math.max(width - leftMargin - rightMargin, 100);

  return (
    <div ref={ref} className="relative w-full overflow-hidden">
      <svg
        aria-label={t('apm.explore.distributionAria', '{unit} 耗时分布，共 {count} 条', { unit: unitLabel, count: items.length })}
        className="block h-32 w-full"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        {/* Reference grid lines */}
        {[0, 0.5, 1].map((ratio) => {
          const y = 16 + ratio * 88;
          return (
            <line
              key={ratio}
              x1={leftMargin}
              x2={width - rightMargin}
              y1={y}
              y2={y}
              stroke="var(--color-border)"
              strokeDasharray="3 4"
              opacity="0.5"
            />
          );
        })}
        {/* Y-axis Latency Scale Labels */}
        <text x={leftMargin - 8} y="20" fill="var(--color-text-3)" fontSize="11" textAnchor="end" className="tabular-nums font-mono">{maxLabel}</text>
        <text x={leftMargin - 8} y="64" fill="var(--color-text-3)" fontSize="11" textAnchor="end" className="tabular-nums font-mono">{midLabel}</text>
        <text x={leftMargin - 8} y="108" fill="var(--color-text-3)" fontSize="11" textAnchor="end" className="tabular-nums font-mono">0ms</text>

        {/* Data Points */}
        {sorted.map((item, index) => {
          const x = sorted.length === 1
            ? leftMargin + chartWidth / 2
            : leftMargin + 8 + (index / (sorted.length - 1)) * (chartWidth - 16);
          const y = 104 - (item.duration_ms / maxDuration) * 88;
          const isError = item.status === 'error';
          return (
            <g key={item.key} className="cursor-pointer transition-opacity hover:opacity-80">
              <title>{`${item.label} · ${formatLatency(item.duration_ms, false, t)} (${isError ? 'Error' : 'OK'})`}</title>
              {isError ? (
                <circle
                  cx={x}
                  cy={y}
                  r="7"
                  fill="none"
                  stroke="var(--color-fail)"
                  strokeWidth="1.5"
                  strokeOpacity="0.4"
                />
              ) : null}
              <circle
                aria-label={t('apm.explore.barAria', '{label}，{duration} 毫秒', { label: item.label, duration: formatNumber(item.duration_ms, 2) })}
                cx={x}
                cy={y}
                fill={isError ? 'var(--color-fail)' : 'var(--color-primary)'}
                r={isError ? '4.5' : '3.5'}
              />
            </g>
          );
        })}
      </svg>
    </div>
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
  labels: { unnamed: string; error: string; ok: string },
): AggregateRow[] {
  const groups = new Map<string, typeof items>();
  items.forEach((item) => {
    const key = dimension === 'service'
      ? item.service_name
      : dimension === 'endpoint'
        ? item.endpoint || labels.unnamed
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
        label: dimension === 'status' ? (key === 'error' ? labels.error : labels.ok) : key,
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
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getServices, getSpans, getTraces, isLoading: authLoading } = useApmApi();
  const unsetParen = t('apm.explore.unsetParen', '(未设置)');
  const statusError = t('apm.status.error', '错误');
  const statusOk = t('apm.status.ok', '正常');
  const initialFilters = useMemo(() => filtersFromSearchParams(searchParams), [searchParams]);
  const [entityMode, setEntityMode] = useState<EntityMode>(
    searchParams.get('entity') === 'traces' ? 'traces' : 'spans',
  );
  const [filters, setFilters] = useState<TraceFilters>(initialFilters);
  const [queryText, setQueryText] = useState(() => serializeFilters(initialFilters));
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [traceItems, setTraceItems] = useState<ApmTraceSummary[]>([]);
  const [spanItems, setSpanItems] = useState<ApmSpanSummary[]>([]);
  const [facets, setFacets] = useState<ResultFacets>(EMPTY_RESULT_FACETS);
  const [resultMode, setResultMode] = useState<ResultMode>('detail');
  const [aggregateDimension, setAggregateDimension] = useState<AggregateDimension>('service');
  const [state, setState] = useState<PageState>('loading');
  const [searching, setSearching] = useState(false);
  const [services, setServices] = useState<ApmService[]>([]);
  const [queryStartedAt, setQueryStartedAt] = useState<string>();
  const [queryEndedAt, setQueryEndedAt] = useState<string>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [durationDraft, setDurationDraft] = useState<{ min: number | null; max: number | null }>({
    min: null,
    max: null,
  });
  const autoSearched = useRef(false);
  const entityModeReady = useRef(false);
  const servicesLoaded = useRef(false);

  const { serviceName } = filters;

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
    if (authLoading) return;
    setSearching(true);
    if (!cursor) {
      setState('loading');
      setPage(1);
      setFacets(EMPTY_RESULT_FACETS);
      setDurationDraft({ min: null, max: null });
    }
    const window = timeWindow(cursor);
    if (entityMode === 'spans') {
      const query: ApmSpanSearchParams = {
        service_namespace: active.namespace || undefined,
        service_name: active.serviceName || undefined,
        environment: active.environment || undefined,
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
          setQueryStartedAt(query.started_at);
          setQueryEndedAt(query.ended_at);
          setState(page.items.length === 0 && !cursor && !page.next_cursor ? 'empty' : 'ready');
        })
        .catch((error) => setState(catalogErrorKind(error)))
        .finally(() => {
          setSearching(false);
        });
      return;
    }
    const query: ApmTraceSearchParams = {
      service_namespace: active.namespace || undefined,
      service_name: active.serviceName || undefined,
      environment: active.environment || undefined,
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
        setQueryStartedAt(query.started_at);
        setQueryEndedAt(query.ended_at);
        setState(page.items.length === 0 && !cursor && !page.next_cursor ? 'empty' : 'ready');
      })
      .catch((error) => setState(catalogErrorKind(error)))
      .finally(() => {
        setSearching(false);
      });
  }, [authLoading, entityMode, filters, getSpans, getTraces, timeWindow]);

  const commitQueryText = useCallback(() => {
    const next = parseFilters(queryText);
    applyFilters(next);
    search(undefined, next);
  }, [applyFilters, queryText, search]);

  const commitDuration = useCallback(() => {
    if (
      durationDraft.min != null
      && durationDraft.max != null
      && durationDraft.min > durationDraft.max
    ) {
      return;
    }
    setFacets((current) => {
      if (current.minDurationMs === durationDraft.min && current.maxDurationMs === durationDraft.max) {
        return current;
      }
      return {
        ...current,
        minDurationMs: durationDraft.min,
        maxDurationMs: durationDraft.max,
      };
    });
  }, [durationDraft]);

  useEffect(() => {
    if (authLoading || servicesLoaded.current) return;
    servicesLoaded.current = true;
    getServices()
      .then((items) => {
        setServices(items);
        if (autoSearched.current) return;
        autoSearched.current = true;
        entityModeReady.current = true;
        search(undefined, initialFilters);
      })
      .catch(() => {
        setServices([]);
        if (!autoSearched.current) {
          autoSearched.current = true;
          entityModeReady.current = true;
          search(undefined, initialFilters);
        }
      });
  }, [authLoading, getServices, initialFilters, search]);

  useEffect(() => {
    if (!authLoading && !servicesLoaded.current && !autoSearched.current) {
      autoSearched.current = true;
      entityModeReady.current = true;
      search();
    }
  }, [authLoading, search]);

  useEffect(() => {
    if (!entityModeReady.current || authLoading) return;
    search();
  }, [entityMode]);

  useEffect(() => {
    if (!autoSearched.current || authLoading) return;
    search();
  }, [timeRange]);

  const traceColumns = useMemo<TableProps<ApmTraceSummary>['columns']>(() => [
    {
      title: t('apm.explore.traceId', 'Trace ID'),
      dataIndex: 'trace_id',
      width: APM_TABLE_COLUMN_WIDTHS.traceId,
      render: (value: string) => (
        <Link
          href={`/apm/explore/traces/${value}`}
          className="truncate font-mono text-xs text-[var(--color-text-3)] transition-colors hover:text-[var(--color-primary)]"
        >
          {value}
        </Link>
      ),
    },
    {
      title: t('apm.explore.entryService', '入口服务'),
      key: 'service',
      width: '18%',
      ellipsis: true,
      render: (_, item) => (
        <span className="flex min-w-0 items-center gap-1.5">
          <HealthDot level={item.status === 'error' ? 1 : 5} showLabel={false} />
          <span className="truncate text-sm font-medium text-[var(--color-text-1)]">{item.service_name}</span>
        </span>
      ),
    },
    {
      title: t('apm.explore.resource', '资源'),
      dataIndex: 'root_span_name',
      width: '32%',
      ellipsis: true,
      responsive: ['md'],
      render: (value) => <span className="truncate font-mono text-xs font-medium text-[var(--color-text-1)]">{value}</span>,
    },
    {
      title: t('apm.explore.totalDuration', '总耗时'),
      dataIndex: 'duration_ms',
      width: APM_TABLE_COLUMN_WIDTHS.metricWide,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['sm'],
      render: (value: number) => <span className="font-medium text-[var(--color-text-1)]">{formatLatency(value, false, t)}</span>,
    },
    {
      title: t('apm.explore.spanCount', '跨度数'),
      dataIndex: 'span_count',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['lg'],
      render: (value: number) => <span className="tabular-nums font-medium">{formatNumber(value)}</span>,
    },
    {
      title: t('apm.common.status', '状态'),
      dataIndex: 'status',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      align: 'center',
      render: (value) => (
        value === 'error'
          ? <Tag bordered={false} color="error">{statusError}</Tag>
          : <Tag bordered={false} color="success">{statusOk}</Tag>
      ),
    },
    {
      title: t('apm.common.time', '时间'),
      dataIndex: 'started_at',
      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
      align: 'right',
      responsive: ['xl'],
      render: (value: string) => (
        <span className="text-xs tabular-nums text-[var(--color-text-3)]" title={formatDateTime(value)}>
          {formatRelativeTime(value, t)}
        </span>
      ),
    },
    {
      title: t('apm.common.operation', '操作'),
      key: 'actions',
      width: APM_TABLE_COLUMN_WIDTHS.singleAction,
      align: 'right',
      fixed: 'right',
      render: (_, item) => (
        <Link
          href={`/apm/explore/traces/${item.trace_id}`}
          className="text-xs font-medium text-[var(--color-primary)] hover:underline"
        >
          {t('apm.explore.traceDetail', '详情')}
        </Link>
      ),
    },
  ], [statusError, statusOk, t]);

  const spanColumns = useMemo<TableProps<ApmSpanSummary>['columns']>(() => [
    {
      title: t('apm.common.service', '服务'),
      key: 'service',
      width: '22%',
      ellipsis: true,
      render: (_, item) => (
        <div className="flex min-w-0 items-center gap-1.5">
          <HealthDot level={item.status === 'error' ? 1 : 5} showLabel={false} />
          <span className="truncate text-sm font-medium text-[var(--color-text-1)]">{item.service_name}</span>
        </div>
      ),
    },
    {
      title: t('apm.explore.resource', '资源'),
      dataIndex: 'name',
      width: '38%',
      ellipsis: true,
      responsive: ['sm'],
      render: (value) => <span className="truncate font-mono text-xs font-medium text-[var(--color-text-1)]">{value}</span>,
    },
    {
      title: 'HTTP',
      width: 100,
      responsive: ['lg'],
      render: (_, item) => {
        if (!item.http_method && !item.http_status_code) {
          return <span className="text-xs text-[var(--color-text-3)]">—</span>;
        }
        const failed = Boolean(item.http_status_code && /^[45]/.test(String(item.http_status_code)));
        return (
          <span className="inline-flex items-center gap-1.5 font-mono text-xs tabular-nums">
            {item.http_method ? (
              <span className="rounded bg-[var(--color-fill-1)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-text-2)]">
                {item.http_method}
              </span>
            ) : null}
            {item.http_status_code ? (
              <span className={failed ? 'font-semibold text-[var(--color-fail)]' : 'text-[var(--color-text-2)]'}>
                {item.http_status_code}
              </span>
            ) : null}
          </span>
        );
      },
    },
    {
      title: t('apm.common.latency', '耗时'),
      dataIndex: 'duration_ms',
      width: APM_TABLE_COLUMN_WIDTHS.metricWide,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['md'],
      render: (value: number) => <span className="font-medium text-[var(--color-text-1)]">{formatLatency(value, false, t)}</span>,
    },
    {
      title: t('apm.common.time', '时间'),
      dataIndex: 'started_at',
      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
      align: 'right',
      responsive: ['xl'],
      render: (value: string) => (
        <span className="text-xs tabular-nums text-[var(--color-text-3)]" title={formatDateTime(value)}>
          {formatRelativeTime(value, t)}
        </span>
      ),
    },
  ], [t]);

  const visibleTraces = useMemo(
    () => traceItems.filter((item) => matchesResultFacets(item, facets)),
    [facets, traceItems],
  );
  const visibleSpans = useMemo(
    () => spanItems.filter((item) => matchesResultFacets(item, facets)),
    [facets, spanItems],
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
      const key = item.environment || unsetParen;
      counts.set(key, (counts.get(key) ?? 0) + 1);
      return counts;
    }, new Map<string, number>())).sort((left, right) => right[1] - left[1]);
  }, [entityMode, spanItems, traceItems, unsetParen]);
  const kindCounts = useMemo(() => {
    if (entityMode !== 'spans') return [] as Array<[string, number]>;
    return Array.from(spanItems.reduce((counts, item) => {
      const key = normalizeSpanKind(item.kind) || 'unspecified';
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
      {
        unnamed: t('apm.explore.unnamed', '(未命名)'),
        error: statusError,
        ok: statusOk,
      },
    ),
    [aggregateDimension, entityMode, statusError, statusOk, t, visibleSpans, visibleTraces],
  );

  useEffect(() => {
    setPage(1);
  }, [aggregateDimension, entityMode, facets, resultMode]);

  const listPagination = {
    current: page,
    pageSize,
    onChange: (nextPage: number, nextPageSize: number) => {
      setPage(nextPageSize === pageSize ? nextPage : 1);
      setPageSize(nextPageSize);
    },
  };

  const aggregateColumns: TableProps<AggregateRow>['columns'] = [
    {
      title: t('apm.explore.group', '分组'),
      dataIndex: 'label',
      width: '28%',
      ellipsis: true,
      render: (value: string) => <span className="font-medium text-[var(--color-text-1)]">{value}</span>,
    },
    {
      title: t('apm.explore.count', '数量'),
      dataIndex: 'count',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      align: 'right',
      className: 'tabular-nums',
      render: (value: number) => <span className="tabular-nums font-medium">{formatNumber(value)}</span>,
    },
    {
      title: t('apm.common.errorRate', '错误率'),
      dataIndex: 'errorRate',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['sm'],
      render: (value: number) => formatErrorRate(value, false, t),
    },
    {
      title: t('apm.explore.avgDuration', '平均耗时'),
      dataIndex: 'avgMs',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['md'],
      render: (value: number) => formatLatency(value, false, t),
    },
    {
      title: t('apm.common.p95', 'P95'),
      dataIndex: 'p95Ms',
      width: APM_TABLE_COLUMN_WIDTHS.compact,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['lg'],
      render: (value: number) => formatLatency(value, false, t),
    },
    {
      title: t('apm.explore.maxDuration', '最大耗时'),
      dataIndex: 'maxMs',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['lg'],
      render: (value: number) => formatLatency(value, false, t),
    },
  ];

  return (
    <ApmRouteShell
      title={t('apm.explore.tracesTitle', '调用链')}
      description={t('apm.explore.tracesDescription', '按服务、环境与时间窗检索 Trace 或 Span，支持明细列表与客户端聚合分析。')}
      dependency="telemetry"
    >
      <div className="flex flex-col gap-4">
        {/* 顶部搜索与过滤控制条卡片 */}
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-3.5 shadow-2xs">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full flex-wrap items-center gap-3">
            <Segmented<EntityMode>
              aria-label={t('apm.explore.entityMode', '调用链查询粒度')}
              options={[
                { value: 'spans', label: 'Spans' },
                { value: 'traces', label: 'Traces' },
              ]}
              value={entityMode}
              onChange={(value) => {
                if (value !== 'spans' && value !== 'traces') return;
                setEntityMode(value);
                setResultMode('detail');
                setTraceItems([]);
                setSpanItems([]);
                setState(serviceName.trim() ? 'loading' : 'idle');
              }}
            />

            <div className="h-4 w-px shrink-0 bg-[var(--color-border)]" aria-hidden="true" />

            <Input
              allowClear
              aria-label={t('apm.explore.filterAria', '调用链过滤条件')}
              className="min-w-0 flex-1 sm:min-w-[280px]"
              placeholder={t('apm.explore.filterPlaceholder', '按 key:value 过滤，如 service:auth environment:lab status:error duration:>=30ms')}
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
            <Button
              type="primary"
              icon={<SearchOutlined aria-hidden="true" />}
              loading={searching}
              onClick={commitQueryText}
            >
              {t('apm.common.query', '查询')}
            </Button>

            <div className="h-4 w-px shrink-0 bg-[var(--color-border)]" aria-hidden="true" />

            <Space size={6}>
              <Select
                aria-label={t('apm.common.timeWindow', '时间窗')}
                className="w-[90px]"
                value={timeRange}
                options={['15m', '1h', '4h', '1d', '7d'].map((value) => ({ value, label: value }))}
                onChange={(value: TimeRange) => {
                  setTimeRange(value);
                  router.replace(`/apm/explore/traces${entityMode === 'spans' ? '?entity=spans' : '?entity=traces'}`);
                }}
              />
              <Select
                aria-label={t('apm.explore.liveTail', '实时尾随')}
                className="w-[88px]"
                disabled
                value="off"
                title={t('apm.explore.liveTailDisabled', '实时尾随尚未开放')}
                options={[{ value: 'off', label: 'off' }]}
              />
            </Space>
          </FilterToolbar>
        </section>

        {state === 'idle' ? (
          <ApmSurface className="!rounded-xl shadow-2xs">
            <CatalogState kind="empty" description={t('apm.explore.idle', '在上方输入 service:... 后回车搜索调用链。')} />
          </ApmSurface>
        ) : state === 'ready' || state === 'empty' ? (
          <div className="grid min-h-0 grid-cols-1 gap-4 xl:grid-cols-[250px_minmax(0,1fr)] xl:items-start">
            {/* 左侧侧边栏快速筛选 */}
            <aside className="self-start rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-2xs">
              <div className="mb-3.5 flex items-center justify-between border-b border-[var(--color-border)] pb-2.5">
                <Typography.Title level={2} className="!mb-0 !text-xs !font-bold !text-[var(--color-text-2)] uppercase tracking-wider">
                  {t('apm.explore.quickFilter', '快速筛选')}
                </Typography.Title>
                {facets.status !== 'all' || facets.serviceName || facets.environment !== undefined || facets.kind || facets.minDurationMs != null || facets.maxDurationMs != null ? (
                  <Button
                    type="link"
                    size="small"
                    className="!p-0 !h-auto text-xs"
                    onClick={() => {
                      setFacets(EMPTY_RESULT_FACETS);
                      setDurationDraft({ min: null, max: null });
                    }}
                  >
                    {t('apm.common.clear', '清空')}
                  </Button>
                ) : null}
              </div>
              <div className="flex flex-col gap-4 divide-y divide-[var(--color-border)]">
                <div>
                  <Typography.Text type="secondary" className="mb-2 block !text-xs font-medium">
                    {t('apm.common.status', '状态')}
                    {facets.status !== 'all' ? (
                      <span className="ml-1.5 font-semibold text-[var(--color-primary)]">(1)</span>
                    ) : null}
                  </Typography.Text>
                  <div className="flex flex-col gap-1">
                    {([
                      { value: 'error' as const, label: statusError, count: statusCounts.error, color: 'var(--color-fail)' },
                      { value: 'ok' as const, label: statusOk, count: statusCounts.ok, color: 'var(--color-success)' },
                    ]).map((item) => (
                      <div
                        key={item.value}
                        className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 transition-colors ${
                          facets.status === item.value
                            ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]'
                            : 'hover:bg-[var(--color-fill-1)]/60'
                        }`}
                      >
                        <Checkbox
                          checked={facets.status === item.value}
                          onChange={(event) => setFacets((current) => ({
                            ...current,
                            status: event.target.checked ? item.value : 'all',
                          }))}
                        >
                          <span className="inline-flex items-center gap-1.5 text-xs">
                            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full" style={{ background: item.color }} />
                            {item.label}
                          </span>
                        </Checkbox>
                        <span className="tabular-nums text-xs text-[var(--color-text-3)]">{item.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="pt-3">
                  <Typography.Text type="secondary" className="mb-2 block !text-xs font-medium">
                    {t('apm.common.service', '服务')}
                    {facets.serviceName ? (
                      <span className="ml-1.5 font-semibold text-[var(--color-primary)]">(1)</span>
                    ) : null}
                  </Typography.Text>
                  <div className="flex flex-col gap-1">
                    {(serviceCounts.length
                      ? serviceCounts
                      : services.map((service) => [service.name, 0] as [string, number])
                    ).slice(0, 8).map(([name, count]) => (
                      <button
                        key={name}
                        type="button"
                        className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
                          facets.serviceName === name
                            ? 'bg-[var(--color-primary-bg-active)] font-medium text-[var(--color-primary)]'
                            : 'hover:bg-[var(--color-fill-1)]/60 text-[var(--color-text-1)]'
                        }`}
                        onClick={() => setFacets((current) => ({
                          ...current,
                          serviceName: current.serviceName === name ? undefined : name,
                        }))}
                      >
                        <span className="truncate max-w-36 text-xs text-inherit" title={name}>{name}</span>
                        <span className="tabular-nums text-xs text-[var(--color-text-3)]">{count}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="pt-3">
                  <Typography.Text type="secondary" className="mb-2 block !text-xs font-medium">
                    {t('apm.common.environment', '环境')}
                    {facets.environment !== undefined ? (
                      <span className="ml-1.5 font-semibold text-[var(--color-primary)]">(1)</span>
                    ) : null}
                  </Typography.Text>
                  <div className="flex flex-col gap-1">
                    {(environmentCounts.length ? environmentCounts : [[unsetParen, 0] as [string, number]]).slice(0, 8).map(([name, count]) => (
                      <button
                        key={name}
                        type="button"
                        className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
                          facets.environment !== undefined && (facets.environment || unsetParen) === name
                            ? 'bg-[var(--color-primary-bg-active)] font-medium text-[var(--color-primary)]'
                            : 'hover:bg-[var(--color-fill-1)]/60 text-[var(--color-text-1)]'
                        }`}
                        onClick={() => {
                          const nextEnvironment = name === unsetParen ? '' : name;
                          setFacets((current) => ({
                            ...current,
                            environment: current.environment === nextEnvironment ? undefined : nextEnvironment,
                          }));
                        }}
                      >
                        <span className="truncate max-w-36 text-xs text-inherit" title={name}>{name}</span>
                        <span className="tabular-nums text-xs text-[var(--color-text-3)]">{count}</span>
                      </button>
                    ))}
                  </div>
                </div>
                {entityMode === 'spans' ? (
                  <div className="pt-3">
                    <Typography.Text type="secondary" className="mb-2 block !text-xs font-medium">
                      {t('apm.explore.spanKind', 'SPAN 类型')}
                      {facets.kind ? (
                        <span className="ml-1.5 font-semibold text-[var(--color-primary)]">(1)</span>
                      ) : null}
                    </Typography.Text>
                    <div className="flex flex-col gap-1">
                      {(kindCounts.length
                        ? kindCounts
                        : SPAN_KINDS.map((value) => [value, 0] as [string, number])
                      ).map(([name, count]) => (
                        <div
                          key={name}
                          className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 transition-colors ${
                            facets.kind === name
                              ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]'
                              : 'hover:bg-[var(--color-fill-1)]/60'
                          }`}
                        >
                          <Checkbox
                            checked={facets.kind === name}
                            onChange={(event) => setFacets((current) => ({
                              ...current,
                              kind: event.target.checked ? name : undefined,
                            }))}
                          >
                            <span className="text-xs uppercase">{name}</span>
                          </Checkbox>
                          <span className="tabular-nums text-xs text-[var(--color-text-3)]">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="pt-3">
                  <Typography.Text type="secondary" className="mb-2 block !text-xs font-medium">{t('apm.common.latency', '耗时')}</Typography.Text>
                  <div className="mt-2 flex items-center gap-1.5">
                    <InputNumber
                      size="small"
                      min={0}
                      controls={false}
                      className="w-full"
                      placeholder="min"
                      value={durationDraft.min}
                      onChange={(value) => setDurationDraft((current) => ({
                        ...current,
                        min: parseDurationInput(value),
                      }))}
                      onBlur={commitDuration}
                      onPressEnter={commitDuration}
                    />
                    <span className="text-xs text-[var(--color-text-3)]">-</span>
                    <InputNumber
                      size="small"
                      min={0}
                      controls={false}
                      className="w-full"
                      placeholder="max"
                      value={durationDraft.max}
                      onChange={(value) => setDurationDraft((current) => ({
                        ...current,
                        max: parseDurationInput(value),
                      }))}
                      onBlur={commitDuration}
                      onPressEnter={commitDuration}
                    />
                    <span className="shrink-0 text-xs text-[var(--color-text-3)]">{t('apm.common.millisecondUnit', 'ms')}</span>
                  </div>
                  {durationDraft.min != null && durationDraft.max != null && durationDraft.min > durationDraft.max ? (
                    <Typography.Text type="danger" className="mt-2 block !text-xs">{t('apm.explore.durationInvalid', '最小耗时不能大于最大耗时')}</Typography.Text>
                  ) : null}
                </div>
              </div>
            </aside>

            {/* 右侧主内容区域 */}
            <div className="flex min-w-0 flex-col gap-4">
              {/* 命中统计横幅卡片 */}
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-2xs">
                <div className="flex flex-wrap items-center gap-6">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-xs font-medium text-[var(--color-text-3)]">
                      {entityMode === 'spans' ? t('apm.explore.spansPerSec', 'spans/s') : t('apm.explore.hitRate', 'traces/s')}
                    </span>
                    <span className="text-xl font-bold tabular-nums text-[var(--color-text-1)]">
                      {formatNumber(hitRate, hitRate >= 10 ? 1 : 2)}
                    </span>
                  </div>
                  <div className="h-8 w-px bg-[var(--color-border)]" aria-hidden="true" />
                  <div className="flex flex-col gap-0.5">
                    <span className="text-xs font-medium text-[var(--color-text-3)]">
                      {t('apm.explore.matchedCount', '命中数量')}
                    </span>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xl font-bold tabular-nums text-[var(--color-text-1)]">
                        {t('apm.explore.hitSummary', '命中 {count} 条 · 窗 {window}', { count: activeItems.length, window: timeRange })}
                      </span>
                    </div>
                  </div>
                </div>

                <Segmented<ResultMode>
                  options={[
                    { value: 'detail', label: t('apm.explore.detail', '明细') },
                    { value: 'aggregate', label: t('apm.explore.aggregate', '聚合') },
                  ]}
                  value={resultMode}
                  onChange={setResultMode}
                />
              </div>

              {resultMode === 'detail' ? (
                <>
                  <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-2xs">
                    <div className="mb-3 flex items-center justify-between border-b border-[var(--color-border)] pb-2.5">
                      <span className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-2)]">
                        {t('apm.explore.durationDistribution', '耗时分布')}
                      </span>
                      <Space size={16}>
                        <span className="inline-flex items-center gap-1.5 text-xs text-[var(--color-text-3)]">
                          <span className="h-2 w-2 rounded-full bg-[var(--color-primary)]" />
                          {statusOk}
                        </span>
                        <span className="inline-flex items-center gap-1.5 text-xs text-[var(--color-text-3)]">
                          <span className="h-2 w-2 rounded-full bg-[var(--color-fail)]" />
                          {statusError}
                        </span>
                      </Space>
                    </div>
                    <TraceDistribution
                      items={distributionItems}
                      unitLabel={entityMode === 'spans' ? 'Span' : 'Trace'}
                    />
                  </div>

                  <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] shadow-2xs">
                    {entityMode === 'spans' ? (
                      <ApmDataTable
                        rowKey="span_id"
                        columns={spanColumns}
                        dataSource={visibleSpans}
                        pagination={listPagination}
                      />
                    ) : (
                      <ApmDataTable
                        rowKey="trace_id"
                        columns={traceColumns}
                        dataSource={visibleTraces}
                        pagination={listPagination}
                      />
                    )}
                  </div>
                </>
              ) : (
                <div className="flex flex-col gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-2xs">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] pb-3">
                    <Typography.Text strong className="text-sm">{t('apm.explore.aggregateAnalysis', '聚合分析')}</Typography.Text>
                    <Segmented<AggregateDimension>
                      size="small"
                      value={aggregateDimension}
                      onChange={setAggregateDimension}
                      options={[
                        { value: 'service', label: t('apm.explore.byService', '按服务') },
                        { value: 'endpoint', label: t('apm.explore.byEndpoint', '按端点') },
                        { value: 'status', label: t('apm.explore.byStatus', '按状态') },
                      ]}
                    />
                  </div>
                  <ApmDataTable
                    rowKey="key"
                    columns={aggregateColumns}
                    dataSource={aggregateRows}
                    pagination={listPagination}
                  />
                </div>
              )}
            </div>
          </div>
        ) : (
          <ApmSurface className="!rounded-xl shadow-2xs">
            <CatalogState
              kind={state}
              onRetry={state === 'forbidden' ? undefined : () => search(undefined, filters)}
            />
          </ApmSurface>
        )}
      </div>
    </ApmRouteShell>
  );
}
