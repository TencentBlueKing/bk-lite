'use client';

import Link from 'next/link';
import { AppstoreOutlined, BellOutlined } from '@ant-design/icons';
import { Tag, Typography } from 'antd';
import {
  formatErrorRate,
  formatThroughput,
  isErrorRateDanger,
} from '@/app/apm/components/metric-format';
import MetricValue from '@/app/apm/components/metric-value';
import ServiceTagOverflow, { type ServiceTagItem } from '@/app/apm/components/service-tag-overflow';
import Sparkline from '@/app/apm/components/home/sparkline';
export type ActiveAlertStatus = 'normal' | 'info' | 'warning' | 'error' | 'critical';

const STATUS_COLOR: Record<ActiveAlertStatus, string> = {
  critical: 'error',
  error: 'error',
  warning: 'warning',
  info: 'processing',
  normal: 'success',
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
      className="group relative h-full min-w-0 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-left transition-colors duration-150 hover:border-[var(--color-primary)] focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--color-primary)]"
    >
      <Link
        href={href}
        aria-label={`查看应用 ${label} 详情`}
        className="absolute inset-0 z-10 cursor-pointer rounded-lg"
      >
        <span className="sr-only">查看应用详情</span>
      </Link>
      <div className="pointer-events-none flex h-full min-w-0 flex-col gap-3 p-4">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2.5">
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <Typography.Text strong ellipsis={{ tooltip: label }} className="!text-sm">
                {label}
              </Typography.Text>
              <Tag
                bordered={false}
                color={STATUS_COLOR[status]}
                className="!m-0 shrink-0 !px-1.5 !text-xs !font-medium !leading-5"
                aria-label={`最高活跃告警：${statusLabel}`}
                title={`最高活跃告警：${statusLabel}`}
              >
                {statusLabel}
              </Tag>
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
              className="inline-flex min-h-10 items-center gap-1 rounded px-2 py-1 text-xs font-medium tabular-nums text-[var(--color-text-2)] no-underline transition-colors duration-150 hover:bg-[var(--color-fill-1)] hover:text-[var(--color-primary)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            >
              <AppstoreOutlined className="text-xs" aria-hidden="true" />
              {services.length}
            </Link>
            <Link
              href={eventsHref}
              aria-label={`应用内 ${alertCount} 个活跃告警，查看告警`}
              title={`应用内 ${alertCount} 个活跃告警`}
              className={`inline-flex min-h-10 items-center gap-1 rounded px-2 py-1 text-xs font-medium tabular-nums no-underline transition-colors duration-150 hover:bg-[var(--color-fill-1)] ${
                alertCount > 0
                  ? 'text-[var(--color-fail)]'
                  : 'text-[var(--color-text-3)] hover:text-[var(--color-primary)]'
              }`}
            >
              <BellOutlined className="text-xs" aria-hidden="true" />
              {alertCount}
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 border-t border-[var(--color-border)] pt-3">
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

        <div className="relative z-20 mt-auto border-t border-[var(--color-border)] pt-3 pointer-events-auto">
          <ServiceTagOverflow services={services} />
        </div>
      </div>
    </article>
  );
}
