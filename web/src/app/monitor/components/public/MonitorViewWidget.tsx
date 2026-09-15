'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import useMonitorApi from '@/app/monitor/api';
import MonitorView from '@/app/monitor/(pages)/view/monitorView';
import { resolveMonitorPublicContext } from './resolveMonitorPublicContext';
import type { MonitorPublicContext } from './resolveMonitorPublicContext';
import { publicWidgetErrorMessage } from './publicWidgetError';

export interface MonitorViewWidgetProps {
  monitorId: string;
  metricKey?: string;
}

const MonitorViewWidget = ({ monitorId, metricKey }: MonitorViewWidgetProps) => {
  const { t } = useTranslation();
  const { lookupInstance, getEffectivePlugins } = useMonitorApi();
  const apisRef = useRef({
    lookupInstance,
    getEffectivePlugins,
  });
  apisRef.current = {
    lookupInstance,
    getEffectivePlugins,
  };
  const [context, setContext] = useState<MonitorPublicContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setContext(null);
    resolveMonitorPublicContext(monitorId, apisRef.current, {
      refresh: reloadKey > 0,
    })
      .then((next) => {
        if (!cancelled) setContext(next);
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
  if (!context.form.instance_id) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <CompactEmptyState description={t('common.noData')} />
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 min-w-0">
      <MonitorView
        monitorObject={context.monitorObject}
        monitorName={context.monitorName}
        plugins={context.plugins}
        form={context.form}
        preferredMetricKey={metricKey}
      />
    </div>
  );
};

export default MonitorViewWidget;
