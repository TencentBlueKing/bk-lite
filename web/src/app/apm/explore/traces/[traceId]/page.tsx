'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';
import {
  ArrowLeftOutlined,
  CloseCircleOutlined,
  CheckCircleOutlined,
  FireFilled,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Col,
  Descriptions,
  Grid,
  Input,
  Progress,
  Row,
  Segmented,
  Space,
  Tag,
  Typography,
} from 'antd';
import type { TableProps } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmDataTable from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import { formatLatency, formatPercentage } from '@/app/apm/components/metric-format';
import type { ApmSpanDetail, ApmTraceDetail } from '@/app/apm/types';
import { HandledRequestError } from '@/utils/request';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready' | 'not-found';
type ViewMode = 'waterfall' | 'flame' | 'list';
type SpanLayoutItem = {
  span: ApmSpanDetail;
  depth: number;
  left: number;
  width: number;
};

const FLAME_ROW_HEIGHT = 24;
const SPAN_ATTRIBUTE_KEY_COLUMN_WIDTH = '58%';
const SPAN_ATTRIBUTE_VALUE_COLUMN_WIDTH = '42%';

const SERVICE_PALETTE = [
  'var(--theme-color-chart-primary)',
  'var(--theme-color-chart-success)',
  'var(--theme-color-chart-warning)',
  'var(--theme-color-chart-error)',
  'color-mix(in srgb, var(--theme-color-chart-primary) 65%, var(--theme-color-chart-success))',
  'color-mix(in srgb, var(--theme-color-chart-success) 65%, var(--theme-color-chart-warning))',
  'color-mix(in srgb, var(--theme-color-chart-warning) 65%, var(--theme-color-chart-error))',
  'color-mix(in srgb, var(--color-primary) 40%, var(--color-fail))',
] as const;

function spanDepth(span: ApmSpanDetail, byId: Map<string, ApmSpanDetail>, seen = new Set<string>()): number {
  if (!span.parent_span_id || seen.has(span.span_id)) return 0;
  const parent = byId.get(span.parent_span_id);
  if (!parent) return 0;
  seen.add(span.span_id);
  return 1 + spanDepth(parent, byId, seen);
}

function serviceColor(serviceName: string, services: string[]): string {
  const index = Math.max(0, services.indexOf(serviceName));
  return SERVICE_PALETTE[index % SERVICE_PALETTE.length];
}

function TraceFlameChart({
  layout,
  services,
  selectedSpanId,
  onSelect,
}: {
  layout: SpanLayoutItem[];
  services: string[];
  selectedSpanId?: string;
  onSelect: (spanId: string) => void;
}) {
  const maxDepth = layout.reduce((max, item) => Math.max(max, item.depth), 0);
  return (
    <div className="w-full overflow-x-auto">
      <div
        className="relative min-h-[72px] min-w-[640px] w-full"
        style={{ height: (maxDepth + 1) * FLAME_ROW_HEIGHT }}
      >
        {layout.map(({ span, depth, left, width }) => {
          const selected = selectedSpanId === span.span_id;
          const color = span.status === 'error'
            ? 'var(--color-fail)'
            : serviceColor(span.service_name, services);
          return (
            <button
              type="button"
              key={span.span_id}
              aria-pressed={selected}
              aria-label={`${span.service_name} · ${span.name}`}
              title={`${span.service_name} · ${span.name}`}
              onClick={() => onSelect(span.span_id)}
              className={`absolute overflow-hidden truncate rounded-sm px-1.5 text-left font-mono text-[11px] leading-[22px] text-white ${
                selected ? 'z-10 ring-2 ring-[var(--color-primary)] ring-offset-1' : ''
              }`}
              style={{
                left: `${left}%`,
                top: depth * FLAME_ROW_HEIGHT,
                width: `${Math.max(width, 0.8)}%`,
                height: FLAME_ROW_HEIGHT - 2,
                background: color,
              }}
            >
              {width > 6 ? span.name : ''}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function KpiStat({
  label,
  value,
  danger,
}: {
  label: string;
  value: string | number;
  danger?: boolean;
}) {
  return (
    <div className="min-w-[96px]">
      <Typography.Text type="secondary" className="!text-xs">{label}</Typography.Text>
      <div
        className={`mt-1 text-base font-semibold tabular-nums leading-6 ${
          danger ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-1)]'
        }`}
      >
        {value}
      </div>
    </div>
  );
}

export default function ApmTraceDetailPage() {
  const { t } = useTranslation();
  const params = useParams<{ traceId: string }>();
  const searchParams = useSearchParams();
  const screens = Grid.useBreakpoint();
  const preferredSpanId = searchParams.get('span_id') ?? undefined;
  const { getTrace, isLoading: authLoading } = useApmApi();
  const [trace, setTrace] = useState<ApmTraceDetail>();
  const [selectedSpanId, setSelectedSpanId] = useState<string>();
  const [state, setState] = useState<PageState>('loading');
  const [viewMode, setViewMode] = useState<ViewMode>('waterfall');
  const [spanQuery, setSpanQuery] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (authLoading || !params.traceId) return;
    setState('loading');
    getTrace(params.traceId)
      .then((value) => {
        setTrace(value);
        const preferred = preferredSpanId
          ? value.spans.find((span) => span.span_id === preferredSpanId)?.span_id
          : undefined;
        setSelectedSpanId(
          preferred
          ?? value.spans.find((span) => span.status === 'error')?.span_id
          ?? value.spans[0]?.span_id,
        );
        setState(value.spans.length ? 'ready' : 'empty');
      })
      .catch((error) => {
        if (error instanceof HandledRequestError && error.status === 404) setState('not-found');
        else setState(catalogErrorKind(error));
      });
  }, [authLoading, getTrace, params.traceId, preferredSpanId, refreshKey]);

  useEffect(() => {
    if (screens.md === false) setViewMode('list');
  }, [screens.md]);

  const services = useMemo(
    () => (trace ? Array.from(new Set(trace.spans.map((span) => span.service_name))) : []),
    [trace],
  );

  const layout = useMemo(() => {
    if (!trace?.spans.length) return [];
    const byId = new Map(trace.spans.map((span) => [span.span_id, span]));
    const traceStart = Math.min(...trace.spans.map((span) => new Date(span.started_at).getTime()));
    const traceEnd = Math.max(...trace.spans.map((span) => new Date(span.started_at).getTime() + span.duration_ms));
    const total = Math.max(1, traceEnd - traceStart);
    return trace.spans.map((span) => ({
      span,
      depth: spanDepth(span, byId),
      left: ((new Date(span.started_at).getTime() - traceStart) / total) * 100,
      width: Math.max(0.5, (span.duration_ms / total) * 100),
    }));
  }, [trace]);

  const serviceBreakdown = useMemo(() => {
    if (!trace?.spans.length) return [];
    const byService = new Map<string, number>();
    trace.spans.forEach((span) => {
      byService.set(span.service_name, (byService.get(span.service_name) ?? 0) + span.duration_ms);
    });
    const total = Array.from(byService.values()).reduce((sum, value) => sum + value, 0) || 1;
    return Array.from(byService.entries())
      .map(([service, duration]) => ({
        service,
        duration,
        percent: (duration / total) * 100,
      }))
      .sort((left, right) => right.duration - left.duration);
  }, [trace]);

  const filteredList = useMemo(() => {
    const normalized = spanQuery.trim().toLocaleLowerCase();
    if (!normalized) return layout;
    return layout.filter(({ span }) => (
      span.name.toLocaleLowerCase().includes(normalized)
      || span.service_name.toLocaleLowerCase().includes(normalized)
    ));
  }, [layout, spanQuery]);

  const selected = trace?.spans.find((span) => span.span_id === selectedSpanId);
  const errorSpans = trace?.spans.filter((span) => span.status === 'error') ?? [];
  const hasError = errorSpans.length > 0;
  const firstErrorId = errorSpans[0]?.span_id;
  const totalDuration = trace?.spans.length
    ? Math.max(...trace.spans.map((span) => new Date(span.started_at).getTime() + span.duration_ms))
      - Math.min(...trace.spans.map((span) => new Date(span.started_at).getTime()))
    : 0;
  const attributeRows = selected
    ? Object.entries(selected.attributes).map(([key, value]) => ({
      key,
      value: typeof value === 'string' ? value : JSON.stringify(value),
    }))
    : [];
  const attributeColumns: TableProps<{ key: string; value: string }>['columns'] = [
    { title: t('apm.trace.attribute', '属性'), dataIndex: 'key', width: SPAN_ATTRIBUTE_KEY_COLUMN_WIDTH, render: (value) => <Typography.Text code className="break-all">{value}</Typography.Text> },
    { title: t('apm.trace.value', '值'), dataIndex: 'value', width: SPAN_ATTRIBUTE_VALUE_COLUMN_WIDTH, render: (value) => <Typography.Text className="break-all">{value}</Typography.Text> },
  ];

  return (
    <ApmRouteShell
      title={t('apm.trace.title', 'Trace 详情')}
      description={t('apm.trace.description', '查看 Span 瀑布、火焰图、服务身份和经过服务端脱敏、截断的属性。')}
      dependency="telemetry"
    >
      {state === 'not-found' ? (
        <ApmSurface padding="none"><CatalogState kind="empty" description={t('apm.trace.notFound', 'Trace 不存在、已超过保留期或当前组织无权访问。')} /></ApmSurface>
      ) : state !== 'ready' ? (
        <ApmSurface padding="none">
          <CatalogState
            kind={state}
            onRetry={state === 'forbidden' ? undefined : () => setRefreshKey((value) => value + 1)}
          />
        </ApmSurface>
      ) : trace ? (
        <div className="flex w-full flex-col gap-4">
          {trace.truncated ? <Alert type="warning" showIcon message={t('apm.trace.truncated', 'Trace 响应已达到安全上限，当前展示部分 Span 或属性。')} /> : null}

          <ApmSurface padding="compact">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <Link href="/apm/explore/traces">
                  <Button aria-label={t('apm.trace.backAria', '返回调用链')} icon={<ArrowLeftOutlined aria-hidden="true" />}>
                    {t('apm.trace.back', '返回')}
                  </Button>
                </Link>
                <div className="min-w-0">
                  <Space wrap size={8}>
                    <Typography.Text type="secondary" className="text-xs">Trace ID</Typography.Text>
                    <Typography.Text copyable className="font-mono text-sm font-medium">
                      {trace.trace_id}
                    </Typography.Text>
                    <Tag
                      bordered={false}
                      color={hasError ? 'error' : 'success'}
                      icon={hasError ? <CloseCircleOutlined aria-hidden="true" /> : <CheckCircleOutlined aria-hidden="true" />}
                    >
                      {hasError ? t('apm.trace.hasError', '含错误') : t('apm.status.ok', '正常')}
                    </Tag>
                  </Space>
                  <Typography.Text type="secondary" className="mt-1 block truncate text-xs">
                    {trace.service_namespace || t('apm.common.unsetNamespace', '未设置 namespace')} · {trace.service_name} · {trace.environment || t('apm.common.unsetEnvironment', '未设置环境')}
                  </Typography.Text>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-x-8 gap-y-3 lg:justify-end">
                <KpiStat label={t('apm.trace.spanCount', 'Span 数')} value={trace.spans.length} />
                <KpiStat label={t('apm.trace.errorSpans', '错误 Span')} value={errorSpans.length} danger={hasError} />
                <KpiStat label={t('apm.trace.serviceCount', '服务数')} value={services.length} />
                <KpiStat label={t('apm.trace.totalDuration', '总耗时')} value={formatLatency(totalDuration, false, t)} />
                {hasError ? (
                  <Button
                    danger
                    icon={<FireFilled aria-hidden="true" />}
                    onClick={() => firstErrorId && setSelectedSpanId(firstErrorId)}
                  >
                    {t('apm.trace.jumpFirstError', '跳到首个错误')}
                  </Button>
                ) : null}
              </div>
            </div>
          </ApmSurface>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={16}>
              <ApmSurface className="h-full">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <Segmented<ViewMode>
                    aria-label={t('apm.trace.viewMode', 'Trace 视图模式')}
                    value={viewMode}
                    onChange={setViewMode}
                    options={[
                      { value: 'waterfall', label: t('apm.trace.waterfall', '瀑布'), disabled: screens.md === false },
                      { value: 'flame', label: t('apm.trace.flame', '火焰图'), disabled: screens.md === false },
                      { value: 'list', label: t('apm.trace.spanList', '跨度列表') },
                    ]}
                  />
                  <Typography.Text type="secondary" className="text-xs tabular-nums">
                    {trace.spans.length} spans
                  </Typography.Text>
                </div>
                {viewMode === 'waterfall' ? (
                  <>
                    <div className="space-y-1 overflow-x-auto">
                      {layout.map(({ span, depth, left, width }) => {
                        const selectedRow = selectedSpanId === span.span_id;
                        const color = span.status === 'error'
                          ? 'var(--color-fail)'
                          : serviceColor(span.service_name, services);
                        return (
                          <button
                            type="button"
                            key={span.span_id}
                            onClick={() => setSelectedSpanId(span.span_id)}
                            aria-pressed={selectedRow}
                            className={`flex min-h-10 w-full items-center rounded-md px-2 py-1 text-left transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)] ${
                              selectedRow
                                ? 'bg-[var(--color-primary-bg-active)]'
                                : 'bg-transparent hover:bg-[var(--color-fill-1)]'
                            }`}
                          >
                            <div className="flex w-64 shrink-0 items-center gap-1.5 truncate text-xs" style={{ paddingLeft: depth * 12 }}>
                              <span
                                className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                                style={{ background: serviceColor(span.service_name, services) }}
                              />
                              <Tag bordered={false} color={span.status === 'error' ? 'error' : 'blue'}>
                                {span.kind.toUpperCase()}
                              </Tag>
                              <span className="truncate font-mono">
                                {span.name}
                              </span>
                              <span className="shrink-0 text-[var(--color-text-3)]">{span.service_name}</span>
                            </div>
                            <div className="relative h-5 min-w-[420px] flex-1 rounded bg-[var(--color-fill-1)]">
                              <div
                                className="absolute top-1 h-3 rounded-sm"
                                style={{
                                  left: `${left}%`,
                                  width: `${width}%`,
                                  background: color,
                                }}
                              />
                            </div>
                            <div className="w-24 text-right text-xs tabular-nums text-[var(--color-text-2)]">
                              {formatLatency(span.duration_ms, false, t)}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </>
                ) : viewMode === 'flame' ? (
                  <TraceFlameChart
                    layout={layout}
                    services={services}
                    selectedSpanId={selectedSpanId}
                    onSelect={setSelectedSpanId}
                  />
                ) : (
                  <>
                    <Input
                      allowClear
                      aria-label={t('apm.trace.searchSpans', '搜索跨度名或服务')}
                      className="mb-3"
                      placeholder={t('apm.trace.searchSpansPlaceholder', '搜索跨度名 / 服务')}
                      prefix={<SearchOutlined className="text-[var(--color-text-3)]" aria-hidden="true" />}
                      value={spanQuery}
                      onChange={(event) => setSpanQuery(event.target.value)}
                    />
                    <div className="overflow-hidden rounded-md border border-[var(--color-border)]">
                      {filteredList.map(({ span, depth }) => {
                        const selectedRow = selectedSpanId === span.span_id;
                        return (
                          <button
                            type="button"
                            key={span.span_id}
                            onClick={() => setSelectedSpanId(span.span_id)}
                            aria-pressed={selectedRow}
                            className={`flex min-h-10 w-full items-center gap-3 border-0 border-b border-b-[var(--color-border)] px-3 py-2 text-left text-sm last:border-b-0 ${
                              selectedRow
                                ? 'bg-[var(--color-primary-bg-active)]'
                                : 'bg-transparent hover:bg-[var(--color-fill-1)]'
                            }`}
                          >
                            <span
                              className="inline-block h-2 w-2 shrink-0 rounded-sm"
                              style={{
                                background: span.status === 'error'
                                  ? 'var(--color-fail)'
                                  : serviceColor(span.service_name, services),
                              }}
                            />
                            <span
                              className="min-w-0 flex-1 truncate font-mono text-[var(--color-text-1)]"
                              style={{ paddingLeft: depth * 12 }}
                            >
                              {span.name}
                            </span>
                            <span className="w-28 shrink-0 truncate text-right text-xs text-[var(--color-text-3)]">
                              {span.service_name}
                            </span>
                            <span
                              className={`w-20 shrink-0 text-right text-xs tabular-nums ${
                                span.status === 'error' || span.duration_ms > 100
                                  ? 'text-[var(--color-fail)]'
                                  : 'text-[var(--color-text-1)]'
                              }`}
                            >
                              {formatLatency(span.duration_ms, false, t)}
                              {span.status === 'error' ? ' ⚠' : ''}
                            </span>
                          </button>
                        );
                      })}
                      {!filteredList.length ? (
                        <div className="px-3 py-6 text-center text-sm text-[var(--color-text-3)]">
                          {t('apm.trace.noMatchingSpans', '没有匹配的跨度')}
                        </div>
                      ) : null}
                    </div>
                  </>
                )}
              </ApmSurface>
            </Col>

            <Col xs={24} xl={8}>
              <div className="sticky top-4 flex flex-col gap-3">
                <ApmSurface padding="compact">
                  <div className="mb-3 flex items-center justify-between">
                    <Typography.Text strong className="!text-xs">{t('apm.trace.serviceBreakdown', '服务耗时分解')}</Typography.Text>
                    <Typography.Text type="secondary" className="!text-[10px]">{t('apm.trace.execTime', '% 执行时间')}</Typography.Text>
                  </div>
                  <div className="flex flex-col gap-2">
                    {serviceBreakdown.map((row) => (
                      <div key={row.service} className="flex items-center gap-2">
                        <span
                          className="inline-block h-2 w-2 shrink-0 rounded-sm"
                          style={{ background: serviceColor(row.service, services) }}
                        />
                        <span className="w-24 shrink-0 truncate font-mono text-xs">{row.service}</span>
                        <Progress
                          className="!mb-0 min-w-0 flex-1"
                          percent={row.percent}
                          showInfo={false}
                          size="small"
                          strokeColor={serviceColor(row.service, services)}
                        />
                        <span className="w-11 shrink-0 text-right text-xs font-medium tabular-nums">
                          {formatPercentage(row.percent, 1)}
                        </span>
                        <span className="w-12 shrink-0 text-right text-xs tabular-nums text-[var(--color-text-3)]">
                          {formatLatency(row.duration, false, t)}
                        </span>
                      </div>
                    ))}
                  </div>
                </ApmSurface>

                <ApmSurface>
                  <Typography.Text strong className="mb-3 block">{t('apm.trace.spanDetail', 'Span 详情')}</Typography.Text>
                  {selected ? (
                    <Space direction="vertical" className="w-full" size="middle">
                      <div>
                        <Typography.Text strong className="font-mono text-sm">{selected.name}</Typography.Text>
                        <div className="mt-2">
                          <Space wrap size={6}>
                            <Tag bordered={false}>{selected.service_name}</Tag>
                            <Tag bordered={false}>{selected.kind.toUpperCase()}</Tag>
                            <Tag bordered={false} color={selected.status === 'error' ? 'error' : 'success'}>
                              {selected.status === 'error' ? 'ERROR' : 'OK'}
                            </Tag>
                          </Space>
                        </div>
                      </div>
                      <Descriptions size="small" column={1}>
                        <Descriptions.Item label={t('apm.trace.totalDuration', '总耗时')}>{formatLatency(selected.duration_ms, false, t)}</Descriptions.Item>
                        <Descriptions.Item label={t('apm.common.service', '服务')}>
                          {selected.service_namespace || t('apm.common.unsetNamespace', '未设置 namespace')} / {selected.service_name}
                        </Descriptions.Item>
                        <Descriptions.Item label={t('apm.trace.instance', '实例')}>{selected.instance_id || t('apm.trace.identityMissing', '身份缺失')}</Descriptions.Item>
                        <Descriptions.Item label={t('apm.common.environment', '环境')}>{selected.environment || t('apm.common.unsetEnvironment', '未设置环境')}</Descriptions.Item>
                        <Descriptions.Item label="Span ID">
                          <Typography.Text copyable className="font-mono text-xs">{selected.span_id}</Typography.Text>
                        </Descriptions.Item>
                      </Descriptions>
                      <div>
                        <Typography.Text type="secondary" className="mb-2 block text-xs">{t('apm.trace.attribute', '属性')}</Typography.Text>
                        <ApmDataTable
                          rowKey="key"
                          size="small"
                          columns={attributeColumns}
                          dataSource={attributeRows}
                          pagination={false}
                          locale={{ emptyText: t('apm.trace.noAttributes', '无属性') }}
                        />
                      </div>
                    </Space>
                  ) : (
                    <Typography.Text type="secondary">{t('apm.trace.selectSpan', '选择一个 Span 查看详情')}</Typography.Text>
                  )}
                </ApmSurface>
              </div>
            </Col>
          </Row>
        </div>
      ) : null}
    </ApmRouteShell>
  );
}
