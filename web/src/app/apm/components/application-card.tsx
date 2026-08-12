'use client';

import Link from 'next/link';
import { AppstoreOutlined, BellOutlined } from '@ant-design/icons';
import { Tag, Tooltip, Typography } from 'antd';
import {
  deriveHealth,
  formatErrorRate,
  formatThroughput,
  HEALTH_LABEL,
  isErrorRateDanger,
  type HealthLevel,
} from '@/app/apm/components/metric-format';
import MetricValue from '@/app/apm/components/metric-value';
import ServiceTagOverflow, { type ServiceTagItem } from '@/app/apm/components/service-tag-overflow';
import Sparkline from '@/app/apm/components/home/sparkline';
import type { CatalogStatus } from '@/app/apm/types';

const RAIL_CLASS: Record<HealthLevel, string> = {
  1: 'bg-[var(--color-fail)]',
  2: 'bg-[var(--theme-color-status-warning)]',
  3: 'bg-[var(--color-text-4)]',
  4: 'bg-[var(--color-text-3)]',
  5: 'bg-[var(--color-success)]',
};

export interface ApplicationCardProps {
  label: string;
  isBuiltin: boolean;
  status: CatalogStatus;
  services: ServiceTagItem[];
  requestRate: number | null;
  errorRate: number | null;
  requestRateTrend: number[];
  errorRateTrend: number[];
  metricUnavailable: boolean;
  alertCount: number;
  timeWindow: string;
  eventsHref: string;
  onOpen: () => void;
  onRetryMetrics?: () => void;
}

export default function ApplicationCard({
  label,
  isBuiltin,
  status,
  services,
  requestRate,
  errorRate,
  requestRateTrend,
  errorRateTrend,
  metricUnavailable,
  alertCount,
  timeWindow,
  eventsHref,
  onOpen,
  onRetryMetrics,
}: ApplicationCardProps) {
  const health = deriveHealth(status, errorRate);
  const errDanger = isErrorRateDanger(errorRate);
  const healthLabel = HEALTH_LABEL[health];
  const showThroughputSpark = requestRateTrend.length > 1;
  const showErrorSpark = errorRateTrend.length > 1;

  return (
    <button
      aria-label={`查看应用 ${label} 下的服务`}
      className="group min-w-0 cursor-pointer rounded-md text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
      type="button"
      onClick={onOpen}
    >
      <div
        className={`flex h-full overflow-hidden border border-[var(--color-border)] bg-[var(--color-bg)] transition-colors duration-150 group-hover:border-[var(--color-primary)] ${
          isBuiltin ? 'border-t-[3px] border-t-dashed border-t-[var(--theme-color-status-warning)]' : ''
        }`}
      >
        <div className={`w-1 shrink-0 ${RAIL_CLASS[health]}`} aria-hidden="true" />
        <div className="flex min-w-0 flex-1 flex-col gap-2.5 p-3.5">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2.5">
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <Typography.Text strong ellipsis={{ tooltip: label }} className="!text-[13px]">
                  {label}
                </Typography.Text>
                <span
                  className={`inline-flex shrink-0 items-center rounded border px-1.5 py-px text-[11px] font-semibold leading-none ${
                    health <= 2
                      ? 'border-[color-mix(in_srgb,var(--color-fail)_28%,var(--color-border))] text-[var(--color-fail)]'
                      : 'border-[var(--color-border)] text-[var(--color-text-3)]'
                  }`}
                  aria-label={healthLabel}
                  title={healthLabel}
                >
                  {healthLabel}
                </span>
                {isBuiltin ? (
                  <Tooltip title="这些服务未设置 service.namespace，平台归入内置未归类应用。">
                    <Tag color="warning" className="!m-0 !text-[11px]">未归类</Tag>
                  </Tooltip>
                ) : null}
              </div>
              <Typography.Text type="secondary" className="mt-1 block !text-xs">
                应用 · {timeWindow}
              </Typography.Text>
            </div>

            <div className="flex shrink-0 items-center gap-1.5">
              <span
                aria-label={`${services.length} 个服务`}
                title={`${services.length} 个服务`}
                className="inline-flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-fill-1)] px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-[var(--color-text-2)]"
              >
                <AppstoreOutlined className="text-[11px]" aria-hidden="true" />
                {services.length}
              </span>
              <Link
                href={eventsHref}
                aria-label={`应用内 ${alertCount} 个活跃告警，查看告警`}
                title={`应用内 ${alertCount} 个活跃告警`}
                className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-semibold tabular-nums no-underline transition-colors duration-150 ${
                  alertCount > 0
                    ? 'border-[var(--color-fail)] text-[var(--color-fail)]'
                    : 'border-[var(--color-border)] text-[var(--color-text-3)] hover:border-[var(--color-primary)]'
                }`}
                onClick={(event) => event.stopPropagation()}
              >
                <BellOutlined className="text-[11px]" aria-hidden="true" />
                {alertCount}
              </Link>
            </div>
          </div>

          <div className="h-px bg-[var(--color-border)]" />

          <div className="grid grid-cols-2 gap-3">
            <div className="min-w-0">
              <Typography.Text type="secondary" className="block !text-[10px] !tracking-wide">
                吞吐量
              </Typography.Text>
              <div className="mt-0.5 flex items-end gap-2">
                <div className="flex min-w-0 items-baseline gap-0.5">
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
              <Typography.Text type="secondary" className="block !text-[10px] !tracking-wide">
                错误率
              </Typography.Text>
              <div className="mt-0.5 flex items-end gap-2">
                <MetricValue
                  size="lg"
                  text={formatErrorRate(errorRate, metricUnavailable)}
                  unavailable={metricUnavailable}
                  danger={errDanger}
                  onRetry={metricUnavailable ? onRetryMetrics : undefined}
                />
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

          <div className="mt-auto border-t border-dashed border-[var(--color-border)] pt-3">
            <ServiceTagOverflow services={services} />
          </div>
        </div>
      </div>
    </button>
  );
}
