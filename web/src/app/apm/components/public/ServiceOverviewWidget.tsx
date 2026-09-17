'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Select, Spin, Table, Tag } from 'antd';
import { ExportOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import useApmApi from '@/app/apm/api';
import HealthDot from '@/app/apm/components/health-dot';
import ServiceLanguageIcon, { serviceLanguageLabel } from '@/app/apm/components/service-language-icon';
import {
  deriveHealth,
  formatDateTime,
  formatErrorRate,
  formatLatency,
  formatThroughput,
  isErrorRateDanger,
} from '@/app/apm/components/metric-format';
import type { ApmService, ApmServiceEndpointRed, ApmServiceRed } from '@/app/apm/types';
import { publicWidgetErrorMessage } from './publicWidgetError';
import { resolvePublicWidgetQueryWindow } from './resolvePublicWidgetQueryWindow';

export interface ServiceOverviewWidgetProps {
  serviceId: string;
  startedAt?: string;
  endedAt?: string;
}

const ServiceOverviewWidget = ({
  serviceId,
  startedAt,
  endedAt,
}: ServiceOverviewWidgetProps) => {
  const { t } = useTranslation();
  const tRef = useRef(t);
  tRef.current = t;

  const { getService, getServiceRed } = useApmApi();
  const apisRef = useRef({ getService, getServiceRed });
  apisRef.current = { getService, getServiceRed };

  const [service, setService] = useState<ApmService | null>(null);
  const [environment, setEnvironment] = useState<string>('');
  const environmentRef = useRef(environment);
  environmentRef.current = environment;

  const [red, setRed] = useState<ApmServiceRed | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [redLoading, setRedLoading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const queryWindow = useMemo(
    () => resolvePublicWidgetQueryWindow(startedAt, endedAt),
    [startedAt, endedAt],
  );
  const queryWindowRef = useRef(queryWindow);
  queryWindowRef.current = queryWindow;

  useEffect(() => {
    let cancelled = false;
    const id = String(serviceId || '').trim();
    if (!id) {
      setLoading(false);
      setError(tRef.current('common.loadFailed'));
      setService(null);
      setRed(null);
      return;
    }
    setLoading(true);
    setError(null);
    const windowSnapshot = queryWindowRef.current;
    apisRef.current
      .getService(id)
      .then(async (next) => {
        if (cancelled) return;
        setService(next);

        const defaultEnv = next.environment_views?.[0]?.environment || '';
        const currentEnv = environmentRef.current;
        const targetEnv =
          currentEnv && next.environment_views?.some((v) => v.environment === currentEnv)
            ? currentEnv
            : defaultEnv;

        setEnvironment(targetEnv);

        const metrics = targetEnv
          ? await apisRef.current.getServiceRed(
            id,
            targetEnv,
            windowSnapshot.startedAt,
            windowSnapshot.endedAt,
          )
          : null;
        if (cancelled) return;
        setRed(metrics);
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(
            publicWidgetErrorMessage(
              requestError,
              tRef.current,
              'apm.common.publicWidgetNotFound',
            ),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [queryWindow.endedAt, queryWindow.startedAt, reloadKey, serviceId]);

  const handleEnvironmentChange = (val: string) => {
    setEnvironment(val);
    if (!service) return;
    setRedLoading(true);
    const windowSnapshot = queryWindowRef.current;
    apisRef.current
      .getServiceRed(
        service.id,
        val,
        windowSnapshot.startedAt,
        windowSnapshot.endedAt,
      )
      .then((metrics) => {
        setRed(metrics);
      })
      .catch(() => {
        setRed(null);
      })
      .finally(() => {
        setRedLoading(false);
      });
  };

  const environmentOptions = useMemo(
    () =>
      (service?.environment_views || []).map((item) => ({
        value: item.environment,
        label: item.environment || t('apm.common.unset'),
      })),
    [service?.environment_views, t],
  );

  const topEndpoints = useMemo(
    () => (red?.top_endpoints || []).slice(0, 5),
    [red?.top_endpoints],
  );

  if (loading) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }

  if (error || !service) {
    return (
      <div className="flex min-h-[280px] flex-col items-center justify-center gap-3">
        <CompactEmptyState description={error || t('common.loadFailed')} />
        <Button onClick={() => setReloadKey((current) => current + 1)}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }

  const health = deriveHealth(service.status, red?.error_rate ?? null);

  return (
    <div className="flex min-h-[280px] min-w-0 flex-col gap-3">
      {/* 1. 顶栏：服务身份、语言、健康态、环境切换与跳转详情 */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3.5 shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--color-fill-2)] text-[var(--color-text-2)]">
            <ServiceLanguageIcon language={service.language} size={20} />
          </div>
          <div className="flex min-w-0 flex-col">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-sm font-semibold text-[var(--color-text-1)]">
                {service.name || '--'}
              </span>
              <HealthDot level={health} showLabel={false} />
              <Tag
                bordered={false}
                className="!m-0 !rounded-full !px-2 !py-0.2 text-[11px] font-medium"
                color={health <= 2 ? 'error' : health === 3 ? 'warning' : 'success'}
              >
                {health <= 2
                  ? t('apm.health.abnormal')
                  : health === 3
                    ? t('apm.health.silent')
                    : t('apm.health.healthy')}
              </Tag>
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-3)]">
              <span>{serviceLanguageLabel(service.language, service.language || '--')}</span>
              {service.application_name && (
                <>
                  <span>·</span>
                  <span>
                    {t('apm.common.application')}:{' '}
                    <span className="text-[var(--color-text-2)]">
                      {service.application_name}
                    </span>
                  </span>
                </>
              )}
              {service.namespace && (
                <>
                  <span>·</span>
                  <span>
                    {t('apm.common.namespace')}:{' '}
                    <span className="text-[var(--color-text-2)]">
                      {service.namespace}
                    </span>
                  </span>
                </>
              )}
              <span>·</span>
              <span className="font-mono text-xs text-[var(--color-text-3)]">
                {formatDateTime(queryWindow.startedAt)} ~ {formatDateTime(queryWindow.endedAt)}
              </span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {environmentOptions.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-3)]">
              <span>{t('apm.common.environment')}:</span>
              <Select
                size="small"
                value={environment || undefined}
                onChange={handleEnvironmentChange}
                options={environmentOptions}
                className="min-w-[110px]"
                popupMatchSelectWidth={false}
              />
            </div>
          )}
          <Button
            size="small"
            type="link"
            icon={<ExportOutlined />}
            className="!p-0 text-xs"
            href={`/apm/services/${service.id}${environment ? `?environment=${encodeURIComponent(environment)}` : ''}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('apm.topology.openService')}
          </Button>
        </div>
      </div>

      <Spin spinning={redLoading}>
        <div className="flex flex-col gap-3">
          {/* 2. RED 黄金指标 4 宫格 */}
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            <div className="flex flex-col gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3 shadow-sm">
              <span className="text-xs font-medium text-[var(--color-text-3)]">
                {t('apm.common.throughput')}
              </span>
              <div className="flex items-baseline gap-1">
                <span className="text-lg font-bold tabular-nums text-[var(--color-text-1)]">
                  {red?.request_rate == null
                    ? '—'
                    : formatThroughput(red.request_rate, false, t)}
                </span>
                {red?.request_rate != null && (
                  <span className="text-xs text-[var(--color-text-3)]">
                    {t('apm.common.requestsPerSecondUnit')}
                  </span>
                )}
              </div>
            </div>

            <div className="flex flex-col gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3 shadow-sm">
              <span className="text-xs font-medium text-[var(--color-text-3)]">
                {t('apm.common.errorRate')}
              </span>
              <div className="flex items-baseline gap-1">
                <span
                  className={`text-lg font-bold tabular-nums ${
                    isErrorRateDanger(red?.error_rate)
                      ? 'text-[var(--color-fail)]'
                      : 'text-[var(--color-text-1)]'
                  }`}
                >
                  {red?.error_rate == null
                    ? '—'
                    : formatErrorRate(red.error_rate, false, t)}
                </span>
              </div>
            </div>

            <div className="flex flex-col gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3 shadow-sm">
              <span className="text-xs font-medium text-[var(--color-text-3)]">
                {t('apm.common.p95')}
              </span>
              <div className="flex items-baseline gap-1">
                <span className="text-lg font-bold tabular-nums text-[var(--color-text-1)]">
                  {red?.p95_ms == null ? '—' : formatLatency(red.p95_ms, false, t)}
                </span>
              </div>
            </div>

            <div className="flex flex-col gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3 shadow-sm">
              <span className="text-xs font-medium text-[var(--color-text-3)]">
                {t('apm.common.p99')}
              </span>
              <div className="flex items-baseline gap-1">
                <span className="text-lg font-bold tabular-nums text-[var(--color-text-1)]">
                  {red?.p99_ms == null ? '—' : formatLatency(red.p99_ms, false, t)}
                </span>
              </div>
            </div>
          </div>

          {/* 3. Top 端点性能列表 */}
          {topEndpoints.length > 0 && (
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3.5 shadow-sm">
              <div className="mb-2.5 flex items-center justify-between">
                <span className="text-xs font-semibold text-[var(--color-text-1)]">
                  {t('apm.serviceDetail.topEndpoints')}
                </span>
                <span className="text-xs text-[var(--color-text-3)]">
                  {topEndpoints.length} {t('apm.common.endpoint')}
                </span>
              </div>
              <Table<ApmServiceEndpointRed>
                rowKey="endpoint"
                size="small"
                pagination={false}
                dataSource={topEndpoints}
                columns={[
                  {
                    title: t('apm.common.endpoint'),
                    dataIndex: 'endpoint',
                    key: 'endpoint',
                    ellipsis: true,
                    render: (endpoint: string) => (
                      <span
                        className="font-mono text-xs font-medium text-[var(--color-text-1)]"
                        title={endpoint}
                      >
                        {endpoint || '--'}
                      </span>
                    ),
                  },
                  {
                    title: t('apm.common.throughput'),
                    dataIndex: 'request_rate',
                    key: 'request_rate',
                    width: 110,
                    render: (val: number | null) => (
                      <span className="font-mono text-xs tabular-nums text-[var(--color-text-2)]">
                        {formatThroughput(val, false, t)} {t('apm.common.requestsPerSecondUnit')}
                      </span>
                    ),
                  },
                  {
                    title: t('apm.common.errorRate'),
                    dataIndex: 'error_rate',
                    key: 'error_rate',
                    width: 90,
                    render: (val: number | null) => (
                      <span
                        className={`font-mono text-xs tabular-nums ${
                          isErrorRateDanger(val)
                            ? 'font-semibold text-[var(--color-fail)]'
                            : 'text-[var(--color-text-2)]'
                        }`}
                      >
                        {formatErrorRate(val, false, t)}
                      </span>
                    ),
                  },
                  {
                    title: t('apm.common.p95'),
                    dataIndex: 'p95_ms',
                    key: 'p95_ms',
                    width: 90,
                    render: (val: number | null) => (
                      <span className="font-mono text-xs tabular-nums text-[var(--color-text-2)]">
                        {formatLatency(val, false, t)}
                      </span>
                    ),
                  },
                  {
                    title: t('apm.common.p99'),
                    dataIndex: 'p99_ms',
                    key: 'p99_ms',
                    width: 90,
                    render: (val: number | null) => (
                      <span className="font-mono text-xs tabular-nums text-[var(--color-text-2)]">
                        {formatLatency(val, false, t)}
                      </span>
                    ),
                  },
                ]}
                className="overflow-hidden rounded-md border border-[var(--color-border)]"
              />
            </div>
          )}
        </div>
      </Spin>
    </div>
  );
};

export default ServiceOverviewWidget;
