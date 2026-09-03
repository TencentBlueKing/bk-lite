'use client';

import { useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { Button, Typography, theme, type TableColumnsType } from 'antd';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import CatalogState, { type CatalogStateKind } from '@/app/apm/components/catalog-state';
import { StatusPill } from '@/app/apm/components/home/section-card';
import {
  formatClockTime,
  formatErrorRate,
  formatLatency,
  formatNumber,
  formatPercentage,
  formatRelativeTime,
  isErrorRateDanger,
} from '@/app/apm/components/metric-format';
import type {
  ApmErrorLocation,
  ApmFailedEndpoint,
  ApmServiceErrorBreakdown,
  ApmServiceErrorType,
  ApmSpanSummary,
} from '@/app/apm/types';
import TimeSeriesComposedChart from '@/components/time-series-composed-chart';
import { useTranslation } from '@/utils/i18n';

type ErrorTabState = CatalogStateKind | 'ready';

const LOCATION_LABEL: Record<ApmErrorLocation, string> = {
  entry: '入口',
  downstream: '调下游',
  internal: '内部',
};

const LOCATION_TONE: Record<ApmErrorLocation, 'info' | 'warning' | 'danger'> = {
  entry: 'info',
  downstream: 'warning',
  internal: 'danger',
};

export default function ServiceErrorTab({
  breakdown,
  state,
  chartData,
  exploreHref,
  onRetry,
}: {
  breakdown?: ApmServiceErrorBreakdown;
  state: ErrorTabState;
  chartData: Array<Record<string, unknown> & { timestamp: string; error_rate_percent: number | null }>;
  exploreHref: string;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  const [endpointFilter, setEndpointFilter] = useState<string>();

  const samples = useMemo(() => {
    const items = breakdown?.recent_failures ?? [];
    return endpointFilter ? items.filter((item) => item.name === endpointFilter) : items;
  }, [breakdown, endpointFilter]);

  const typeColumns: TableColumnsType<ApmServiceErrorType> = [
    {
      title: t('apm.serviceDetail.errorType', '类型'),
      dataIndex: 'error_type',
      render: (_value, row) => (
        <div className="flex min-w-0 flex-col gap-0.5" title={row.error_type}>
          <span className="truncate font-mono text-xs font-semibold text-[var(--color-text-1)]">{row.error_type}</span>
          {row.message ? <span className="truncate text-[11px] text-[var(--color-text-3)]">{row.message}</span> : null}
        </div>
      ),
    },
    {
      title: t('apm.serviceDetail.errorLocation', '发生位置'),
      dataIndex: 'location',
      width: 104,
      align: 'center',
      render: (value: ApmErrorLocation) => (
        <StatusPill
          tone={LOCATION_TONE[value]}
          label={t(`apm.serviceDetail.location.${value}`, LOCATION_LABEL[value])}
        />
      ),
    },
    {
      title: t('apm.serviceDetail.occurrenceCount', '次数'),
      dataIndex: 'count',
      width: 96,
      align: 'right',
      className: 'tabular-nums',
      render: (value: number) => <span className="font-semibold text-[var(--color-text-1)]">{formatNumber(value)}</span>,
    },
    {
      title: t('apm.common.time', '时间'),
      dataIndex: 'last_seen_at',
      width: 96,
      align: 'right',
      render: (value: string) => (
        <span className="text-xs text-[var(--color-text-3)]">{formatRelativeTime(value, t)}</span>
      ),
    },
    {
      title: t('apm.errors.sampleTraces', '样本调用链'),
      dataIndex: 'sample_traces',
      width: 180,
      render: (traces: ApmServiceErrorType['sample_traces']) => <SampleTraceLinks traces={traces} />,
    },
  ];

  const sampleColumns: TableColumnsType<ApmSpanSummary> = [
    {
      title: t('apm.common.endpoint', '端点'),
      dataIndex: 'name',
      ellipsis: true,
      render: (value: string, row) => (
        <Link href={`/apm/explore/traces/${row.trace_id}`} className="font-mono text-xs font-medium text-[var(--color-text-1)] transition-colors hover:text-[var(--color-primary)]">
          {value}
        </Link>
      ),
    },
    {
      title: 'HTTP',
      key: 'http',
      width: 100,
      render: (_value, row) => {
        const status = row.http_status_code ?? '';
        const failed = /^[45]/.test(status);
        return (
          <span className={`inline-flex items-center gap-1.5 font-mono text-xs tabular-nums ${failed ? 'font-semibold text-[var(--color-fail)]' : 'text-[var(--color-text-2)]'}`}>
            {row.http_method ? (
              <span className="rounded bg-[var(--color-fill-1)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-text-2)]">
                {row.http_method}
              </span>
            ) : null}
            {status ? (
              <span className={failed ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-2)]'}>
                {status}
              </span>
            ) : null}
            {!row.http_method && !status ? '—' : null}
          </span>
        );
      },
    },
    {
      title: t('apm.explore.totalDuration', '总耗时'),
      dataIndex: 'duration_ms',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      className: 'tabular-nums',
      align: 'right',
      render: (value: number) => <span className="font-medium text-[var(--color-text-1)]">{formatLatency(value, false, t)}</span>,
    },
    {
      title: t('apm.common.time', '时间'),
      dataIndex: 'started_at',
      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
      align: 'right',
      render: (value: string) => (
        <span className="text-xs text-[var(--color-text-3)]">{formatRelativeTime(value, t)}</span>
      ),
    },
    {
      title: t('apm.common.operation', '操作'),
      key: 'operation',
      width: 60,
      align: 'right',
      render: (_value, row) => (
        <Link href={`/apm/explore/traces/${row.trace_id}`} className="text-xs font-medium text-[var(--color-primary)] hover:underline">
          {t('apm.common.detail', '详情')}
        </Link>
      ),
    },
  ];

  if (state !== 'ready') {
    return (
      <CatalogState
        kind={state}
        description={state === 'empty' ? t('apm.serviceDetail.noEntryRequests', '本窗无入口请求') : undefined}
        onRetry={state === 'forbidden' || state === 'empty' ? undefined : onRetry}
      />
    );
  }

  if (!breakdown || breakdown.data_state === 'no_data') {
    return (
      <CatalogState
        kind="empty"
        description={t('apm.serviceDetail.noEntryRequests', '本窗无入口请求')}
      />
    );
  }

  if ((breakdown.error_count ?? 0) === 0) {
    return (
      <div className="flex flex-col gap-4">
        <ErrorTabHeader breakdown={breakdown} chartData={chartData} />
        <CatalogState kind="empty" description={t('apm.serviceDetail.noFailures', '本窗无失败请求')} />
      </div>
    );
  }

  const endpointRows: Array<ApmFailedEndpoint & { isOther?: boolean }> = [
    ...breakdown.failed_endpoints,
    ...(breakdown.other_error_count
      ? [{ endpoint: '__other__', error_count: breakdown.other_error_count, request_count: 0, error_rate: null, isOther: true }]
      : []),
  ];

  return (
    <div className="flex flex-col gap-5">
      <ErrorTabHeader breakdown={breakdown} chartData={chartData} />

      {/* 错误原因（全宽展示根因与堆栈） */}
      <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-2xs">
        <SectionTitle hint={t('apm.serviceDetail.errorReasonHint', '按错误类型统计，一次失败请求可能对应多个错误')}>
          {t('apm.serviceDetail.errorReasons', '错误原因')}
        </SectionTitle>
        <ApmDataTable
          size="small"
          rowKey="error_type"
          pagination={false}
          columns={typeColumns}
          dataSource={breakdown.error_types}
        />
      </section>

      {/* 失败端点与调用链样本（联动下钻） */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 lg:items-start">
        {/* 左侧：失败端点列表 */}
        <section className="flex min-w-0 flex-col gap-3 lg:col-span-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <SectionTitle>{t('apm.serviceDetail.failedEndpoints', '失败端点')}</SectionTitle>
            <span className="text-xs text-[var(--color-text-3)]">
              {t('apm.serviceDetail.endpointsCount', '{count} 个端点', { count: breakdown.failed_endpoints.length })}
            </span>
          </div>
          <div className="flex flex-col gap-2">
            {endpointRows.map((row) => {
              const selected = !row.isOther && endpointFilter === row.endpoint;
              const isDanger = isErrorRateDanger(row.error_rate);
              const ratePercent = row.error_rate !== null ? Math.min(Math.max(row.error_rate * 100, 0), 100) : 0;

              return (
                <button
                  key={row.endpoint}
                  type="button"
                  disabled={row.isOther}
                  onClick={() => {
                    if (row.isOther) return;
                    setEndpointFilter((current) => (current === row.endpoint ? undefined : row.endpoint));
                  }}
                  className={`group flex flex-col gap-2 rounded-lg border p-3 text-left transition-all ${
                    row.isOther
                      ? 'cursor-default border-dashed border-[var(--color-border)] bg-[var(--color-fill-1)]/30 text-[var(--color-text-3)]'
                      : selected
                        ? 'cursor-pointer border-[var(--color-primary)] bg-[var(--color-primary-bg-active)] shadow-2xs'
                        : 'cursor-pointer border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-fill-1)]/40'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate font-mono text-xs font-semibold text-[var(--color-text-1)]" title={row.endpoint}>
                      {row.isOther
                        ? t('apm.serviceDetail.otherErrors', '其他 {count} 次', { count: row.error_count })
                        : row.endpoint}
                    </span>
                    <span
                      className={`shrink-0 font-mono text-xs font-bold tabular-nums ${
                        row.isOther || row.error_rate == null
                          ? 'text-[var(--color-text-3)]'
                          : isDanger
                            ? 'text-[var(--color-fail)]'
                            : 'text-[var(--color-warning)]'
                      }`}
                    >
                      {formatErrorRate(row.error_rate, false, t)}
                    </span>
                  </div>
                  {row.isOther ? null : (
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center justify-between text-[11px] tabular-nums text-[var(--color-text-3)]">
                        <span>
                          {t('apm.serviceDetail.failedCountLabel', '失败 {count}', { count: formatNumber(row.error_count) })}
                        </span>
                        <span>
                          {row.request_count == null ? '—' : t('apm.serviceDetail.totalRequestsLabel', '共 {count} 次', { count: formatNumber(row.request_count) })}
                        </span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-fill-2)]">
                        <div
                          className="h-full rounded-full transition-[width] duration-300"
                          style={{
                            width: `${ratePercent}%`,
                            background: isDanger ? 'var(--color-fail)' : 'var(--color-warning)',
                          }}
                        />
                      </div>
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </section>

        {/* 右侧：最近失败调用链 */}
        <section className="flex min-w-0 flex-col gap-3 lg:col-span-8 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-2xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <SectionTitle>
              {t('apm.serviceDetail.recentFailures', '最近 {count} 条', { count: samples.length })}
            </SectionTitle>
            <div className="flex flex-wrap items-center gap-2">
              {endpointFilter ? (
                <Button type="link" size="small" onClick={() => setEndpointFilter(undefined)}>
                  {t('apm.serviceDetail.clearEndpointFilter', '清除端点筛选')}
                </Button>
              ) : null}
              <Link href={exploreHref}>
                <Button type="link" size="small">{t('apm.serviceDetail.openErrorExplore', '在错误分析中打开')}</Button>
              </Link>
            </div>
          </div>
          <ApmDataTable
            size="small"
            rowKey={(row) => `${row.trace_id}:${row.span_id}`}
            pagination={false}
            columns={sampleColumns}
            dataSource={samples}
          />
        </section>
      </div>
    </div>
  );
}

function SectionTitle({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <div className="flex min-w-0 flex-wrap items-baseline gap-2">
      <Typography.Title level={3} className="!mb-0 !text-sm !font-semibold !leading-5 !text-[var(--color-text-1)]">
        {children}
      </Typography.Title>
      {hint ? <span className="text-xs text-[var(--color-text-3)]">{hint}</span> : null}
    </div>
  );
}

function SampleTraceLinks({ traces }: { traces: ApmServiceErrorType['sample_traces'] }) {
  const { t } = useTranslation();
  if (!traces.length) return <span className="text-xs text-[var(--color-text-3)]">—</span>;
  const endpoint = traces[0].endpoint;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="truncate font-mono text-xs text-[var(--color-text-2)]" title={endpoint}>{endpoint}</span>
      <div className="flex flex-wrap gap-1">
        {traces.map((sample, index) => (
          <Link
            key={`${sample.trace_id}:${sample.span_id}`}
            href={`/apm/explore/traces/${sample.trace_id}`}
            aria-label={t('apm.serviceDetail.sampleTraceLabel', '{endpoint} · 样本 {n}', {
              endpoint: sample.endpoint,
              n: index + 1,
            })}
            className="inline-flex h-5 min-w-5 items-center justify-center rounded bg-[var(--color-fill-1)] px-1.5 font-mono text-[11px] font-medium tabular-nums text-[var(--color-primary)] transition-colors duration-150 hover:bg-[var(--color-primary-bg-active)] hover:text-[var(--color-primary)]"
          >
            {index + 1}
          </Link>
        ))}
      </div>
    </div>
  );
}

function ErrorTabHeader({
  breakdown,
  chartData,
}: {
  breakdown: ApmServiceErrorBreakdown;
  chartData: Array<Record<string, unknown> & { timestamp: string; error_rate_percent: number | null }>;
}) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const errorDanger = isErrorRateDanger(breakdown.error_rate);

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-2xs">
      {/* 顶部 4 项核心指标 */}
      <div className="grid grid-cols-2 gap-3 divide-y sm:grid-cols-4 sm:divide-x sm:divide-y-0 divide-[var(--color-border)] pb-2">
        <div className="flex flex-col gap-1 sm:px-3 first:pl-0">
          <span className="text-xs font-medium text-[var(--color-text-3)]">{t('apm.serviceDetail.entryRequests', '入口请求')}</span>
          <span className="text-2xl font-bold tabular-nums text-[var(--color-text-1)]">
            {formatNumber(breakdown.request_count ?? 0)}
          </span>
        </div>
        <div className="flex flex-col gap-1 pt-2 sm:pt-0 sm:px-3">
          <span className="text-xs font-medium text-[var(--color-text-3)]">{t('apm.serviceDetail.failureCount', '失败次数')}</span>
          <span className={`text-2xl font-bold tabular-nums ${breakdown.error_count ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-1)]'}`}>
            {formatNumber(breakdown.error_count ?? 0)}
          </span>
        </div>
        <div className="flex flex-col gap-1 pt-2 sm:pt-0 sm:px-3">
          <span className="text-xs font-medium text-[var(--color-text-3)]">{t('apm.common.errorRate', '错误率')}</span>
          <span className={`text-2xl font-bold tabular-nums ${errorDanger ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-1)]'}`}>
            {formatErrorRate(breakdown.error_rate, false, t)}
          </span>
        </div>
        <div className="flex flex-col gap-1 pt-2 sm:pt-0 sm:px-3 last:pr-0">
          <span className="text-xs font-medium text-[var(--color-text-3)]">{t('apm.serviceDetail.impactedEndpoints', '受影响端点')}</span>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold tabular-nums text-[var(--color-text-1)]">
              {(breakdown.failed_endpoints ?? []).length}
            </span>
            <span className="text-xs text-[var(--color-text-3)]">{t('apm.common.countUnit', '个')}</span>
          </div>
        </div>
      </div>

      {/* 错误率趋势大图 */}
      <div className="flex flex-col gap-2 border-t border-[var(--color-border)] pt-3">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[var(--color-text-1)]">{t('apm.serviceDetail.errorTrend', '错误率趋势')}</span>
            <span className="hidden sm:inline text-xs text-[var(--color-text-3)]">
              {t('apm.serviceDetail.errorRateReconcile', '本窗 {requests} 次入口请求 · {errors} 次失败 · 错误率 {rate}', {
                requests: formatNumber(breakdown.request_count ?? 0),
                errors: formatNumber(breakdown.error_count ?? 0),
                rate: formatErrorRate(breakdown.error_rate, false, t),
              })}
            </span>
          </div>
          <span className="inline-flex items-center gap-1.5 text-xs text-[var(--color-text-3)]">
            <span className="h-2 w-2 rounded-full bg-[var(--color-fail)]" />
            {t('apm.common.errorRatePercent', '错误率 %')}
          </span>
        </div>
        <div
          className="h-[160px] w-full"
          role="img"
          aria-label={t('apm.serviceDetail.errorTrend', '错误率趋势')}
        >
          <TimeSeriesComposedChart
            data={chartData}
            xDataKey="timestamp"
            getXLabel={(item) => (item.timestamp ? formatClockTime(String(item.timestamp), false) : '')}
            legendVisible={false}
            xAxisBoundaryGap={false}
            grid={{ top: 12, right: 16, bottom: 24, left: 48, containLabel: false }}
            yAxes={[{ formatter: (value) => formatPercentage(value, value >= 10 || value === 0 ? 0 : 1) }]}
            series={[{
              name: t('apm.common.errorRatePercent', '错误率 %'),
              type: 'line',
              dataKey: 'error_rate_percent',
              color: token.colorError,
              showArea: true,
              lineWidth: 1.5,
              showSymbol: false,
            }]}
            surfaceProps={{ emptyStateProps: { description: t('apm.serviceDetail.noRedTrend', '当前时间窗暂无 RED 趋势点') } }}
          />
        </div>
      </div>
    </div>
  );
}
