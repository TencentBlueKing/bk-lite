'use client';

import Link from 'next/link';
import { AppstoreOutlined, BellOutlined } from '@ant-design/icons';
import { Typography } from 'antd';
import {
  formatErrorRate,
  formatThroughput,
  isErrorRateDanger,
} from '@/app/apm/components/metric-format';
import MetricValue from '@/app/apm/components/metric-value';
import ServiceTagOverflow, { type ServiceTagItem } from '@/app/apm/components/service-tag-overflow';
import Sparkline from '@/app/apm/components/home/sparkline';
export type ActiveAlertStatus = 'normal' | 'info' | 'warning' | 'error' | 'critical';

const RAIL_CLASS: Record<ActiveAlertStatus, string> = {
  critical: 'bg-[var(--color-fail)]',
  error: 'bg-[var(--color-fail)]',
  warning: 'bg-[var(--theme-color-status-warning)]',
  info: 'bg-[var(--color-primary)]',
  normal: 'bg-[var(--color-success)]',
};

const STATUS_LABEL: Record<ActiveAlertStatus, string> = {
  critical: '严重',
  error: '错误',
  warning: '警告',
  info: '提示',
  normal: '正常',
};

export interface ApplicationCardProps {
  label: string;
  status: ActiveAlertStatus;
  services: ServiceTagItem[];
  requestRate: number | null;
  errorRate: number | null;
  requestRateTrend: number[];
  errorRateTrend: number[];
  metricUnavailable: boolean;
  alertCount: number;
  timeWindow: string;
  servicesHref: string;
  eventsHref: string;
  href: string;
  onRetryMetrics?: () => void;
}

export default function ApplicationCard({
  label,
  status,
  services,
  requestRate,
  errorRate,
  requestRateTrend,
  errorRateTrend,
  metricUnavailable,
  alertCount,
  timeWindow,
  servicesHref,
  eventsHref,
  href,
  onRetryMetrics,
}: ApplicationCardProps) {
  const errDanger = isErrorRateDanger(errorRate);
  const statusLabel = STATUS_LABEL[status];
  const showThroughputSpark = requestRateTrend.length > 1;
  const showErrorSpark = errorRateTrend.length > 1;

  return (
    <article
      className="group relative min-w-0 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-left transition-colors duration-150 hover:border-[var(--color-primary)] focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--color-primary)]"
    >
      <Link
        href={href}
        aria-label={`查看应用 ${label} 详情`}
        className="absolute inset-0 z-10 cursor-pointer rounded-lg"
      >
        <span className="sr-only">查看应用详情</span>
      </Link>
      <div className="pointer-events-none flex h-full overflow-hidden">
        <div className={`w-1 shrink-0 ${RAIL_CLASS[status]}`} aria-hidden="true" />
        <div className="flex min-w-0 flex-1 flex-col gap-2.5 p-3.5">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2.5">
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <Typography.Text strong ellipsis={{ tooltip: label }} className="!text-sm">
                  {label}
                </Typography.Text>
                <span
                  className={`inline-flex shrink-0 items-center rounded border px-1.5 py-px text-xs font-semibold leading-none ${
                    status === 'critical' || status === 'error'
                      ? 'border-[color-mix(in_srgb,var(--color-fail)_28%,var(--color-border))] text-[var(--color-fail)]'
                      : 'border-[var(--color-border)] text-[var(--color-text-3)]'
                  }`}
                  aria-label={`最高活跃告警：${statusLabel}`}
                  title={`最高活跃告警：${statusLabel}`}
                >
                  {statusLabel}
                </span>
              </div>
              <Typography.Text type="secondary" className="mt-1 block !text-xs">
                应用 · {timeWindow}
              </Typography.Text>
            </div>

            <div className="relative z-20 flex shrink-0 items-center gap-1.5 pointer-events-auto">
              <Link
                href={servicesHref}
                aria-label={`应用内 ${services.length} 个服务，查看服务`}
                title={`应用内 ${services.length} 个服务`}
                className="inline-flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-fill-1)] px-1.5 py-0.5 text-xs font-semibold tabular-nums text-[var(--color-text-2)] no-underline transition-colors duration-150 hover:border-[var(--color-primary)] hover:text-[var(--color-primary)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
              >
                <AppstoreOutlined className="text-xs" aria-hidden="true" />
                {services.length}
              </Link>
              <Link
                href={eventsHref}
                aria-label={`应用内 ${alertCount} 个活跃告警，查看告警`}
                title={`应用内 ${alertCount} 个活跃告警`}
                className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-semibold tabular-nums no-underline transition-colors duration-150 ${
                  alertCount > 0
                    ? 'border-[var(--color-fail)] text-[var(--color-fail)]'
                    : 'border-[var(--color-border)] text-[var(--color-text-3)] hover:border-[var(--color-primary)]'
                }`}
              >
                <BellOutlined className="text-xs" aria-hidden="true" />
                {alertCount}
              </Link>
            </div>
          </div>

          <div className="h-px bg-[var(--color-border)]" />

          <div className="grid grid-cols-2 gap-3">
            <div className="min-w-0">
              <Typography.Text type="secondary" className="block !text-xs">
                吞吐量
              </Typography.Text>
              <div className="mt-0.5 flex items-end gap-2">
                <div className={`flex min-w-0 items-baseline gap-0.5 ${metricUnavailable ? 'relative z-20 pointer-events-auto' : ''}`}>
                  <MetricValue
                    size="lg"
                    text={formatThroughput(requestRate, metricUnavailable)}
                    unavailable={metricUnavailable}
                    onRetry={metricUnavailable ? onRetryMetrics : undefined}
                  />
                  {requestRate !== null ? (
                    <span className="text-xs text-[var(--color-text-3)]">/s</span>
                  ) : null}
                </div>
                {showThroughputSpark ? (
                  <div title="吞吐量趋势" className="mb-0.5">
                    <Sparkline
                      data={requestRateTrend}
                      width={88}
                      height={22}
                      fit="fixed"
                      color="var(--color-primary)"
                      kind="area"
                    />
                  </div>
                ) : null}
              </div>
            </div>
            <div className="min-w-0">
              <Typography.Text type="secondary" className="block !text-xs">
                错误率
              </Typography.Text>
              <div className="mt-0.5 flex items-end gap-2">
                <div className={metricUnavailable ? 'relative z-20 pointer-events-auto' : ''}>
                  <MetricValue
                    size="lg"
                    text={formatErrorRate(errorRate, metricUnavailable)}
                    unavailable={metricUnavailable}
                    danger={errDanger}
                    onRetry={metricUnavailable ? onRetryMetrics : undefined}
                  />
                </div>
                {showErrorSpark ? (
                  <div title="错误率趋势" className="mb-0.5">
                    <Sparkline
                      data={errorRateTrend}
                      width={88}
                      height={22}
                      fit="fixed"
                      color={errDanger ? 'var(--color-fail)' : 'var(--color-primary)'}
                      kind="area"
                    />
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          <div className="relative z-20 mt-auto border-t border-dashed border-[var(--color-border)] pt-3 pointer-events-auto">
            <ServiceTagOverflow services={services} />
          </div>
        </div>
      </div>
    </article>
  );
}
