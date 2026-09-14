'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import useMonitorApi from '@/app/monitor/api';
import MonitorAlarm from '@/app/monitor/(pages)/view/monitorAlarm';
import { resolveMonitorPublicContext } from './resolveMonitorPublicContext';
import type { MonitorPublicContext } from './resolveMonitorPublicContext';
import type { MetricItem } from '@/app/monitor/types';
import { publicWidgetErrorMessage } from './publicWidgetError';

export interface AlertListWidgetProps {
  monitorId: string;
}

const AlertListWidget = ({ monitorId }: AlertListWidgetProps) => {
  const { t } = useTranslation();
  const {
    lookupInstance,
    getEffectivePlugins,
    getMonitorMetrics,
  } = useMonitorApi();
  const apisRef = useRef({
    lookupInstance,
    getEffectivePlugins,
    getMonitorMetrics,
  });
  apisRef.current = {
    lookupInstance,
    getEffectivePlugins,
    getMonitorMetrics,
  };
  const [context, setContext] = useState<MonitorPublicContext | null>(null);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setContext(null);
    const { getMonitorMetrics: fetchMetrics } = apisRef.current;
    resolveMonitorPublicContext(monitorId, apisRef.current, {
      refresh: reloadKey > 0,
    })
      .then(async (next) => {
        const metricPage = await fetchMetrics({
          monitor_object_id: next.monitorObject,
          page_size: 1000,
        });
        if (cancelled) return;
        setContext(next);
        setMetrics(metricPage.items || []);
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(
            publicWidgetErrorMessage(
              requestError,
              t,
              'monitor.views.publicWidgetNotFound',
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
  }, [monitorId, reloadKey]);

  if (loading) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (error || !context) {
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
    <MonitorAlarm
      monitorObject={context.monitorObject}
      monitorName={context.monitorName}
      plugins={context.plugins}
      form={context.form}
      metrics={metrics}
      objects={context.objects}
      readOnly
    />
  );
};

export default AlertListWidget;
