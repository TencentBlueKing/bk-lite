'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { Button, Select, Segmented, Spin, Table, Tag } from 'antd';
import { ExportOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useApmApi from '@/app/apm/api';
import { formatDateTime, formatLatency } from '@/app/apm/components/metric-format';
import type { ApmService, ApmTraceSummary } from '@/app/apm/types';
import { publicWidgetErrorMessage } from './publicWidgetError';
import { resolvePublicWidgetQueryWindow } from './resolvePublicWidgetQueryWindow';

export interface CallChainWidgetProps {
  serviceId: string;
  startedAt?: string;
  endedAt?: string;
}

type TraceStatusFilter = 'all' | 'error';

const CallChainWidget = ({
  serviceId,
  startedAt,
  endedAt,
}: CallChainWidgetProps) => {
  const { t } = useTranslation();
  const tRef = useRef(t);
  tRef.current = t;

  const { convertToLocalizedTime } = useLocalizedTime();
  const { getService, getTraces } = useApmApi();
  const apisRef = useRef({ getService, getTraces });
  apisRef.current = { getService, getTraces };

  const [service, setService] = useState<ApmService | null>(null);
  const [environment, setEnvironment] = useState<string>('');
  const environmentRef = useRef(environment);
  environmentRef.current = environment;

  const [statusFilter, setStatusFilter] = useState<TraceStatusFilter>('all');
  const statusFilterRef = useRef(statusFilter);
  statusFilterRef.current = statusFilter;

  const [items, setItems] = useState<ApmTraceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tracesLoading, setTracesLoading] = useState(false);
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
      setItems([]);
      return;
    }
    setLoading(true);
    setError(null);
    const windowSnapshot = queryWindowRef.current;
    apisRef.current
      .getService(id)
      .then(async (nextService) => {
        if (cancelled) return;
        setService(nextService);

        const defaultEnv = nextService.environment_views?.[0]?.environment || '';
        const currentEnv = environmentRef.current;
        const targetEnv =
          currentEnv && nextService.environment_views?.some((v) => v.environment === currentEnv)
            ? currentEnv
            : defaultEnv;

        setEnvironment(targetEnv);

        const traces = await apisRef.current.getTraces({
          service_namespace: nextService.namespace,
          service_name: nextService.name,
          environment: targetEnv || undefined,
          started_at: windowSnapshot.startedAt,
          ended_at: windowSnapshot.endedAt,
          limit: 20,
          ...(statusFilterRef.current === 'error' ? { status: 'error' } : {}),
        });
        if (cancelled) return;
        setItems(traces?.items || []);
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

  const fetchTraces = (targetEnv: string, targetStatus: TraceStatusFilter) => {
    if (!service) return;
    setTracesLoading(true);
    const windowSnapshot = queryWindowRef.current;
    apisRef.current
      .getTraces({
        service_namespace: service.namespace,
        service_name: service.name,
        environment: targetEnv || undefined,
        started_at: windowSnapshot.startedAt,
        ended_at: windowSnapshot.endedAt,
        limit: 20,
        ...(targetStatus === 'error' ? { status: 'error' } : {}),
      })
      .then((traces) => {
        setItems(traces?.items || []);
      })
      .catch(() => {
        setItems([]);
      })
      .finally(() => {
        setTracesLoading(false);
      });
  };

  const handleEnvironmentChange = (val: string) => {
    setEnvironment(val);
    fetchTraces(val, statusFilter);
  };

  const handleStatusFilterChange = (val: TraceStatusFilter) => {
    setStatusFilter(val);
    fetchTraces(environment, val);
  };

  const environmentOptions = useMemo(
    () =>
      (service?.environment_views || []).map((item) => ({
        value: item.environment,
        label: item.environment || t('apm.common.unset'),
      })),
    [service?.environment_views, t],
  );

  const exploreHref = useMemo(() => {
    if (!service) return '/apm/explore/traces';
    const params = new URLSearchParams({
      service_namespace: service.namespace,
      service_name: service.name,
      started_at: queryWindow.startedAt,
      ended_at: queryWindow.endedAt,
    });
    if (environment) {
      params.set('environment', environment);
    }
    if (statusFilter === 'error') {
      params.set('status', 'error');
    }
    return `/apm/explore/traces?${params.toString()}`;
  }, [environment, queryWindow.endedAt, queryWindow.startedAt, service, statusFilter]);

  const columns = useMemo(
    () => [
      {
        title: t('apm.common.endpoint'),
        dataIndex: 'root_span_name',
        key: 'root_span_name',
        ellipsis: true,
        render: (val: string) => (
          <span
            className="font-mono text-xs font-semibold text-[var(--color-text-1)]"
            title={val}
          >
            {val || '--'}
          </span>
        ),
      },
      {
        title: t('apm.common.status'),
        dataIndex: 'status',
        key: 'status',
        width: 80,
        align: 'center' as const,
        render: (status: ApmTraceSummary['status']) =>
          status === 'error' ? (
            <Tag bordered={false} color="error" className="m-0 text-xs">
              {t('apm.status.error')}
            </Tag>
          ) : (
            <Tag bordered={false} color="success" className="m-0 text-xs">
              {t('apm.status.ok')}
            </Tag>
          ),
      },
      {
        title: t('apm.common.latency'),
        dataIndex: 'duration_ms',
        key: 'duration_ms',
        width: 96,
        align: 'right' as const,
        className: 'tabular-nums',
        render: (val: number | null) => (
          <span className="font-mono text-xs font-medium text-[var(--color-text-1)]">
            {formatLatency(val, false, t)}
          </span>
        ),
      },
      {
        title: t('apm.explore.spanCount'),
        dataIndex: 'span_count',
        key: 'span_count',
        width: 80,
        align: 'right' as const,
        className: 'tabular-nums',
        render: (val: number | null) => (
          <span className="font-mono text-xs text-[var(--color-text-3)]">
            {val != null ? val : '--'}
          </span>
        ),
      },
      {
        title: t('apm.explore.traceId'),
        dataIndex: 'trace_id',
        key: 'trace_id',
        width: 240,
        ellipsis: true,
        render: (val: string) => (
          <Link
            href={`/apm/explore/traces/${val}`}
            target="_blank"
            rel="noopener noreferrer"
            className="truncate font-mono text-xs text-[var(--color-primary)] hover:underline"
            title={val}
          >
            {val}
          </Link>
        ),
      },
      {
        title: t('apm.common.time'),
        dataIndex: 'started_at',
        key: 'started_at',
        width: 160,
        render: (val: string) => (
          <span className="font-mono text-xs text-[var(--color-text-3)]">
            {val ? convertToLocalizedTime(val) : '--'}
          </span>
        ),
      },
    ],
    [convertToLocalizedTime, t],
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

  return (
    <div className="flex min-h-[280px] min-w-0 flex-col gap-3">
      {/* 顶栏薄条：服务名、应用、时间窗、环境选择、状态过滤与在探索中打开 */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3.5 shadow-sm">
        <div className="flex min-w-0 flex-col">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-semibold text-[var(--color-text-1)]">
              {service.name || '--'}
            </span>
            {service.application_name && (
              <span className="text-xs text-[var(--color-text-3)]">
                ({service.application_name})
              </span>
            )}
          </div>
          <div className="mt-0.5 font-mono text-xs text-[var(--color-text-3)]">
            {formatDateTime(queryWindow.startedAt)} ~ {formatDateTime(queryWindow.endedAt)}
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

          <Segmented<TraceStatusFilter>
            size="small"
            value={statusFilter}
            onChange={(val) => handleStatusFilterChange(val)}
            options={[
              { label: t('apm.common.all'), value: 'all' },
              { label: t('apm.common.errorOnly'), value: 'error' },
            ]}
          />

          <Button
            size="small"
            type="link"
            icon={<ExportOutlined />}
            className="!p-0 text-xs"
            href={exploreHref}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('apm.explore.openInExplore')}
          </Button>
        </div>
      </div>

      {/* 表格容器 */}
      <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] shadow-sm">
        <Spin spinning={tracesLoading}>
          {items.length === 0 ? (
            <div className="flex min-h-[200px] items-center justify-center p-6">
              <CompactEmptyState description={t('common.noData')} />
            </div>
          ) : (
            <Table
              rowKey="trace_id"
              size="small"
              dataSource={items}
              columns={columns}
              pagination={
                items.length > 10
                  ? {
                    pageSize: 10,
                    size: 'small',
                    showSizeChanger: false,
                    className: '!my-2.5 !mr-3',
                  }
                  : false
              }
              scroll={{ x: 'max-content' }}
            />
          )}
        </Spin>
      </div>
    </div>
  );
};

export default CallChainWidget;
