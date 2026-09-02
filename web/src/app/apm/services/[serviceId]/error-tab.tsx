'use client';

import { useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { Button, Typography, theme, type TableColumnsType } from 'antd';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import CatalogState, { type CatalogStateKind } from '@/app/apm/components/catalog-state';
import { StatusPill } from '@/app/apm/components/home/section-card';
import { errorRateBarColor } from '@/app/apm/components/home/top5-bar-chart';
import {
  formatErrorRate,
  formatLatency,
  formatNumber,
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
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate font-mono text-sm text-[var(--color-text-1)]">{row.error_type}</span>
          {row.message ? <span className="truncate text-xs text-[var(--color-text-3)]">{row.message}</span> : null}
        </div>
      ),
    },
    {
      title: t('apm.serviceDetail.occurrenceCount', '次数'),
      dataIndex: 'count',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      className: 'tabular-nums',
      render: (value: number) => formatNumber(value),
    },
    {
      title: t('apm.serviceDetail.errorLocation', '发生位置'),
      dataIndex: 'location',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      render: (value: ApmErrorLocation) => (
        <StatusPill
          tone={LOCATION_TONE[value]}
          label={t(`apm.serviceDetail.location.${value}`, LOCATION_LABEL[value])}
        />
      ),
    },
    {
      title: t('apm.common.time', '时间'),
      dataIndex: 'last_seen_at',
      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
      render: (value: string) => (
        <span className="text-[var(--color-text-3)]">{formatRelativeTime(value, t)}</span>
      ),
    },
    {
      title: t('apm.errors.sampleTraces', '样本调用链'),
      dataIndex: 'sample_traces',
      width: APM_TABLE_COLUMN_WIDTHS.resource,
      render: (traces: ApmServiceErrorType['sample_traces']) => <SampleTraceLinks traces={traces} />,
    },
  ];

  const sampleColumns: TableColumnsType<ApmSpanSummary> = [
    {
      title: t('apm.common.endpoint', '端点'),
      dataIndex: 'name',
      ellipsis: true,
      render: (value: string, row) => (
        <Link href={`/apm/explore/traces/${row.trace_id}`} className="font-mono text-xs text-[var(--color-text-1)] hover:text-[var(--color-primary)]">
          {value}
        </Link>
      ),
    },
    {
      title: 'HTTP',
      key: 'http',
      width: APM_TABLE_COLUMN_WIDTHS.compact,
      render: (_value, row) => {
        const status = row.http_status_code ?? '';
        const failed = /^[45]/.test(status);
        return (
          <span className={`font-mono text-xs tabular-nums ${failed ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-2)]'}`}>
            {[row.http_method, status].filter(Boolean).join(' ') || '—'}
          </span>
        );
      },
    },
    {
      title: t('apm.explore.totalDuration', '总耗时'),
      dataIndex: 'duration_ms',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      className: 'tabular-nums',
      render: (value: number) => formatLatency(value, false, t),
    },
    {
      title: t('apm.common.time', '时间'),
      dataIndex: 'started_at',
      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
      render: (value: string) => (
        <span className="text-[var(--color-text-3)]">{formatRelativeTime(value, t)}</span>
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
  const maxEndpointErrors = Math.max(...endpointRows.map((row) => row.error_count), 1);

  return (
    <div className="flex flex-col gap-5">
      <ErrorTabHeader breakdown={breakdown} chartData={chartData} />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 lg:items-start">
        <section className="flex min-w-0 flex-col gap-3">
          <SectionTitle>{t('apm.serviceDetail.failedEndpoints', '失败端点')}</SectionTitle>
          <div className="flex flex-col">
            {endpointRows.map((row, index) => {
              const selected = !row.isOther && endpointFilter === row.endpoint;
              const share = (row.error_count / maxEndpointErrors) * 100;
              const barColor = errorRateBarColor(row.error_rate ?? 0);
              return (
                <button
                  key={row.endpoint}
                  type="button"
                  disabled={row.isOther}
                  onClick={() => {
                    if (row.isOther) return;
                    setEndpointFilter((current) => (current === row.endpoint ? undefined : row.endpoint));
                  }}
                  className={`flex min-h-11 flex-col gap-2 px-2 py-2.5 text-left transition-colors duration-150 ${
                    index < endpointRows.length - 1 ? 'border-b border-[var(--color-border)]' : ''
                  } ${
                    row.isOther
                      ? 'cursor-default text-[var(--color-text-3)]'
                      : selected
                        ? 'cursor-pointer bg-[var(--color-fill-2)]'
                        : 'cursor-pointer hover:bg-[var(--color-fill-1)]'
                  }`}
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="min-w-0 truncate font-mono text-xs text-[var(--color-text-1)]">
                      {row.isOther
                        ? t('apm.serviceDetail.otherErrors', '其他 {count} 次', { count: row.error_count })
                        : row.endpoint}
                    </span>
                    <span className="shrink-0 text-xs font-medium tabular-nums" style={row.error_rate == null ? undefined : { color: barColor }}>
                      {formatErrorRate(row.error_rate, false, t)}
                    </span>
                  </div>
                  {row.isOther ? null : (
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-sm bg-[var(--color-fill-2)]">
                        <div
                          className="h-full rounded-sm transition-[width] duration-200"
                          style={{
                            width: `${share}%`,
                            background: 'color-mix(in srgb, var(--color-fail) 72%, transparent)',
                          }}
                        />
                      </div>
                      <span className="shrink-0 text-xs tabular-nums text-[var(--color-text-3)]">
                        {formatNumber(row.error_count)} / {row.request_count == null ? '—' : formatNumber(row.request_count)}
                      </span>
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </section>
        <section className="flex min-w-0 flex-col gap-3">
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
      </div>
      <section className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <SectionTitle>
            {t('apm.serviceDetail.recentFailures', '最近 {count} 条', { count: breakdown.recent_failures.length })}
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
      <span className="truncate font-mono text-xs text-[var(--color-text-2)]">{endpoint}</span>
      <div className="flex flex-wrap gap-1">
        {traces.map((sample, index) => (
          <Link
            key={`${sample.trace_id}:${sample.span_id}`}
            href={`/apm/explore/traces/${sample.trace_id}`}
            aria-label={t('apm.serviceDetail.sampleTraceLabel', '{endpoint} · 样本 {n}', {
              endpoint: sample.endpoint,
              n: index + 1,
            })}
            className="inline-flex min-h-6 min-w-6 items-center justify-center rounded px-2 text-xs tabular-nums text-[var(--color-primary)] transition-colors duration-150 hover:bg-[var(--color-fill-2)]"
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
    <div className="flex flex-col gap-3 rounded-lg bg-[var(--color-fill-1)] p-3 lg:flex-row lg:items-stretch">
      <p className="sr-only">
        {t('apm.serviceDetail.errorRateReconcile', '本窗 {requests} 次入口请求 · {errors} 次失败 · 错误率 {rate}', {
          requests: formatNumber(breakdown.request_count ?? 0),
          errors: formatNumber(breakdown.error_count ?? 0),
          rate: formatErrorRate(breakdown.error_rate, false, t),
        })}
      </p>
      <div className="grid min-w-0 flex-1 grid-cols-3 gap-3">
        <HeaderStat
          label={t('apm.serviceDetail.entryRequests', '入口请求')}
          value={formatNumber(breakdown.request_count ?? 0)}
        />
        <HeaderStat
          label={t('apm.serviceDetail.failureCount', '失败次数')}
          value={formatNumber(breakdown.error_count ?? 0)}
          emphasize={Boolean(breakdown.error_count)}
        />
        <HeaderStat
          label={t('apm.common.errorRate', '错误率')}
          value={formatErrorRate(breakdown.error_rate, false, t)}
          emphasize={errorDanger}
        />
      </div>
      <div
        className="h-[80px] min-w-0 lg:w-64 lg:shrink-0"
        role="img"
        aria-label={t('apm.serviceDetail.errorTrend', '错误率趋势')}
      >
        <TimeSeriesComposedChart
          data={chartData}
          xDataKey="timestamp"
          getXLabel={() => ''}
          legendVisible={false}
          xAxisBoundaryGap={false}
          axisLabelFontSize={0}
          grid={{ top: 8, right: 4, bottom: 4, left: 4, containLabel: false }}
          yAxes={[{ formatter: () => '', splitLine: false }]}
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
  );
}

function HeaderStat({
  label,
  value,
  emphasize = false,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-xs text-[var(--color-text-3)]">{label}</span>
      <span className={`text-xl font-semibold tabular-nums leading-6 ${emphasize ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-1)]'}`}>
        {value}
      </span>
    </div>
  );
}
