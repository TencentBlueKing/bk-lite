'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Spin, Table } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useApmApi from '@/app/apm/api';
import type { ApmTraceSummary } from '@/app/apm/types';
import { publicWidgetErrorMessage } from './publicWidgetError';

export interface CallChainWidgetProps {
  serviceId: string;
}

const recentWindow = () => {
  const ended = new Date();
  const started = new Date(ended.getTime() - 60 * 60 * 1000);
  return {
    startedAt: started.toISOString(),
    endedAt: ended.toISOString(),
  };
};

const CallChainWidget = ({ serviceId }: CallChainWidgetProps) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getService, getTraces } = useApmApi();
  const apisRef = useRef({ getService, getTraces });
  apisRef.current = { getService, getTraces };
  const [items, setItems] = useState<ApmTraceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const id = String(serviceId || '').trim();
    if (!id) {
      setLoading(false);
      setError(t('common.loadFailed'));
      setItems([]);
      return;
    }
    setLoading(true);
    setError(null);
    setItems([]);
    const { startedAt, endedAt } = recentWindow();
    apisRef.current
      .getService(id)
      .then(async (service) => {
        const traces = await apisRef.current.getTraces({
          service_namespace: service.namespace,
          service_name: service.name,
          environment: service.environment_views?.[0]?.environment,
          started_at: startedAt,
          ended_at: endedAt,
          limit: 20,
        });
        if (cancelled) return;
        setItems(traces?.items || []);
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(
            publicWidgetErrorMessage(
              requestError,
              t,
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
  }, [reloadKey, serviceId, t]);

  if (loading) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex min-h-[280px] flex-col items-center justify-center gap-3">
        <CompactEmptyState description={error} />
        <Button onClick={() => setReloadKey((current) => current + 1)}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }
  if (!items.length) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <CompactEmptyState description={t('common.noData')} />
      </div>
    );
  }

  return (
    <div className="min-h-[280px] min-w-0">
      <Table
        rowKey="trace_id"
        size="small"
        pagination={false}
        dataSource={items}
        columns={[
          {
            title: t('apm.explore.traceId'),
            dataIndex: 'trace_id',
            key: 'trace_id',
          },
          {
            title: t('apm.common.time'),
            dataIndex: 'started_at',
            key: 'started_at',
            render: (value: string) =>
              value ? convertToLocalizedTime(value) : '--',
          },
          {
            title: t('apm.common.latency'),
            dataIndex: 'duration_ms',
            key: 'duration_ms',
            render: (value: number) =>
              value == null ? '--' : `${value} ms`,
          },
          {
            title: t('apm.common.status'),
            dataIndex: 'status',
            key: 'status',
          },
        ]}
      />
    </div>
  );
};

export default CallChainWidget;
