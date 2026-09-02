'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Button, Tag, Typography, theme, type TableColumnsType } from 'antd';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import CatalogState, { type CatalogStateKind } from '@/app/apm/components/catalog-state';
import {
  formatErrorRate,
  formatLatency,
  formatNumber,
  formatRelativeTime,
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
  const { token } = theme.useToken();
  const [endpointFilter, setEndpointFilter] = useState<string>();

  const samples = useMemo(() => {
    const items = breakdown?.recent_failures ?? [];
    return endpointFilter ? items.filter((item) => item.name === endpointFilter) : items;
  }, [breakdown, endpointFilter]);

  const endpointColumns: TableColumnsType<ApmFailedEndpoint & { isOther?: boolean }> = [
    {
      title: t('apm.common.endpoint', '端点'),
      dataIndex: 'endpoint',
      ellipsis: true,
      render: (value: string, row) => (
        row.isOther
          ? t('apm.serviceDetail.otherErrors', '其他 {count} 次', { count: row.error_count })
          : <span className="font-mono text-xs">{value}</span>
      ),
    },
    {
      title: t('apm.serviceDetail.failureCount', '失败次数'),
      dataIndex: 'error_count',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      className: 'tabular-nums',
      render: (value: number) => formatNumber(value),
    },
    {
      title: t('apm.serviceDetail.requestCount', '请求次数'),
      dataIndex: 'request_count',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      className: 'tabular-nums',
      render: (value: number | null) => (value == null ? '—' : formatNumber(value)),
    },
    {
      title: t('apm.common.errorRate', '错误率'),
      dataIndex: 'error_rate',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      render: (value: number | null) => formatErrorRate(value, false, t),
    },
  ];

  const typeColumns: TableColumnsType<ApmServiceErrorType> = [
    {
      title: t('apm.serviceDetail.errorType', '类型'),
      dataIndex: 'error_type',
      render: (_value, row) => (
        <div className="flex min-w-0 flex-col">
          <span className="font-mono text-sm">{row.error_type}</span>
          {row.message ? <span className="text-xs text-[var(--color-text-3)]">{row.message}</span> : null}
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
        <Tag bordered={false}>{t(`apm.serviceDetail.location.${value}`, LOCATION_LABEL[value])}</Tag>
      ),
    },
    {
      title: t('apm.common.time', '时间'),
      dataIndex: 'last_seen_at',
      width: APM_TABLE_COLUMN_WIDTHS.relativeTime,
      render: (value: string) => formatRelativeTime(value, t),
    },
    {
      title: t('apm.errors.sampleTraces', '样本调用链'),
      dataIndex: 'sample_traces',
      render: (samples: ApmServiceErrorType['sample_traces']) => (
        <div className="flex flex-col gap-1">
          {samples.map((sample) => (
            <Link
              key={`${sample.trace_id}:${sample.span_id}`}
              href={`/apm/explore/traces/${sample.trace_id}`}
              className="font-mono text-xs text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
            >
              {sample.endpoint}
            </Link>
          ))}
        </div>
      ),
    },
  ];

  const sampleColumns: TableColumnsType<ApmSpanSummary> = [
    {
      title: t('apm.common.endpoint', '端点'),
      dataIndex: 'name',
      ellipsis: true,
      render: (value: string, row) => (
        <Link href={`/apm/explore/traces/${row.trace_id}`} className="font-mono text-xs hover:text-[var(--color-primary)]">
          {value}
        </Link>
      ),
    },
    {
      title: 'HTTP',
      key: 'http',
      width: APM_TABLE_COLUMN_WIDTHS.compact,
      render: (_value, row) => (
        <span className="font-mono text-xs text-[var(--color-text-2)]">
          {[row.http_method, row.http_status_code].filter(Boolean).join(' ') || '—'}
        </span>
      ),
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
      render: (value: string) => formatRelativeTime(value, t),
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
    <div className="flex flex-col gap-6">
      <ErrorTabHeader breakdown={breakdown} chartData={chartData} />
      <section className="flex flex-col gap-2">
        <Typography.Text strong>{t('apm.serviceDetail.failedEndpoints', '失败端点')}</Typography.Text>
        <ApmDataTable
          rowKey="endpoint"
          pagination={false}
          columns={endpointColumns}
          dataSource={endpointRows}
          onRow={(row) => ({
            onClick: () => {
              if (row.isOther) return;
              setEndpointFilter((current) => (current === row.endpoint ? undefined : row.endpoint));
            },
          })}
          rowClassName={(row) => (
            !row.isOther && endpointFilter === row.endpoint
              ? 'cursor-pointer bg-[var(--color-fill-2)]'
              : row.isOther ? '' : 'cursor-pointer'
          )}
        />
      </section>
      <section className="flex flex-col gap-2">
        <div>
          <Typography.Text strong>{t('apm.serviceDetail.errorReasons', '错误原因')}</Typography.Text>
          <Typography.Text type="secondary" className="ml-2 !text-xs">
            {t('apm.serviceDetail.errorReasonHint', '按错误类型统计，一次失败请求可能对应多个错误')}
          </Typography.Text>
        </div>
        <ApmDataTable rowKey="error_type" pagination={false} columns={typeColumns} dataSource={breakdown.error_types} />
      </section>
      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Typography.Text strong>
            {t('apm.serviceDetail.recentFailures', '最近 {count} 条', { count: breakdown.recent_failures.length })}
            {endpointFilter ? (
              <Button type="link" size="small" onClick={() => setEndpointFilter(undefined)}>
                {t('apm.serviceDetail.clearEndpointFilter', '清除端点筛选')}
              </Button>
            ) : null}
          </Typography.Text>
          <Link href={exploreHref}>
            <Button type="link" size="small">{t('apm.serviceDetail.openErrorExplore', '在错误分析中打开')}</Button>
          </Link>
        </div>
        <ApmDataTable
          rowKey={(row) => `${row.trace_id}:${row.span_id}`}
          pagination={false}
          columns={sampleColumns}
          dataSource={samples}
        />
      </section>
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
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Typography.Text type="secondary" className="!text-xs">
        {t('apm.serviceDetail.errorRateReconcile', '本窗 {requests} 次入口请求 · {errors} 次失败 · 错误率 {rate}', {
          requests: formatNumber(breakdown.request_count ?? 0),
          errors: formatNumber(breakdown.error_count ?? 0),
          rate: formatErrorRate(breakdown.error_rate, false, t),
        })}
      </Typography.Text>
      <div className="h-12 w-48">
        <TimeSeriesComposedChart
          data={chartData}
          xDataKey="timestamp"
          yAxes={[{ formatter: () => '' }]}
          series={[{ name: t('apm.common.errorRatePercent', '错误率 %'), type: 'line', dataKey: 'error_rate_percent', color: token.colorError, showArea: true }]}
          surfaceProps={{ emptyStateProps: { description: t('apm.serviceDetail.noRedTrend', '当前时间窗暂无 RED 趋势点') } }}
        />
      </div>
    </div>
  );
}
