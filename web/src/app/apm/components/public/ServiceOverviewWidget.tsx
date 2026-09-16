'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Descriptions, Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import useApmApi from '@/app/apm/api';
import type { ApmService, ApmServiceRed } from '@/app/apm/types';
import { publicWidgetErrorMessage } from './publicWidgetError';

export interface ServiceOverviewWidgetProps {
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

const ServiceOverviewWidget = ({ serviceId }: ServiceOverviewWidgetProps) => {
  const { t } = useTranslation();
  const { getService, getServiceRed } = useApmApi();
  const apisRef = useRef({ getService, getServiceRed });
  apisRef.current = { getService, getServiceRed };
  const [service, setService] = useState<ApmService | null>(null);
  const [red, setRed] = useState<ApmServiceRed | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const id = String(serviceId || '').trim();
    if (!id) {
      setLoading(false);
      setError(t('common.loadFailed'));
      setService(null);
      setRed(null);
      return;
    }
    setLoading(true);
    setError(null);
    setService(null);
    setRed(null);
    const { startedAt, endedAt } = recentWindow();
    apisRef.current
      .getService(id)
      .then(async (next) => {
        const environment = next.environment_views?.[0]?.environment || '';
        const metrics = environment
          ? await apisRef.current.getServiceRed(
            id,
            environment,
            startedAt,
            endedAt,
          )
          : null;
        if (cancelled) return;
        setService(next);
        setRed(metrics);
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
    <div className="min-h-[280px] min-w-0">
      <Descriptions column={1} size="small">
        <Descriptions.Item label={t('apm.common.service')}>
          {service.name || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('apm.common.application')}>
          {service.application_name || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('apm.common.environment')}>
          {red?.environment || service.environment_views?.[0]?.environment || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('apm.common.throughput')}>
          {red?.request_rate == null ? '--' : red.request_rate}
        </Descriptions.Item>
        <Descriptions.Item label={t('apm.common.errorRate')}>
          {red?.error_rate == null ? '--' : red.error_rate}
        </Descriptions.Item>
        <Descriptions.Item label={t('apm.common.p95')}>
          {red?.p95_ms == null ? '--' : `${red.p95_ms} ms`}
        </Descriptions.Item>
      </Descriptions>
    </div>
  );
};

export default ServiceOverviewWidget;
