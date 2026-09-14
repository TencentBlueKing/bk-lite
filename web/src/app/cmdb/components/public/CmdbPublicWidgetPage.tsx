'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Spin } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import {
  canShowCrossModulePublicWidget,
  hasAppAccess,
  useAppWidget,
  useLazyAppWidget,
} from '@/context/appCapabilities';
import type { AppWidgetKey } from '@/context/appCapabilities';
import { useClientData } from '@/context/client';
import { useInstanceApi } from '@/app/cmdb/api';

type InstUuidWidget = React.ComponentType<{ instUuid: string }>;
type MonitorIdWidget = React.ComponentType<{ monitorId: string }>;

export function CmdbPublicWidgetPage({
  widgetKey,
  identifierProp,
}: {
  widgetKey: AppWidgetKey;
  identifierProp: 'instUuid' | 'monitorId';
}) {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { clientData } = useClientData();
  const hasOpsAnalysis = hasAppAccess(clientData, 'ops-analysis');
  const instUuid = resolveCmdbInstUuid(searchParams.get('inst_uuid')) || '';
  const widget = useAppWidget(widgetKey);
  const { getInstanceDetail } = useInstanceApi();
  const getInstanceDetailRef = useRef(getInstanceDetail);
  getInstanceDetailRef.current = getInstanceDetail;
  const [monitorId, setMonitorId] = useState('');
  const [resolvingMonitorId, setResolvingMonitorId] = useState(
    identifierProp === 'monitorId',
  );

  useEffect(() => {
    if (identifierProp !== 'monitorId') {
      setResolvingMonitorId(false);
      setMonitorId('');
      return;
    }
    if (!instUuid) {
      setResolvingMonitorId(false);
      setMonitorId('');
      return;
    }
    let cancelled = false;
    setResolvingMonitorId(true);
    getInstanceDetailRef.current(instUuid)
      .then((detail: { monitor_id?: string }) => {
        if (!cancelled) setMonitorId(String(detail?.monitor_id || '').trim());
      })
      .catch(() => {
        if (!cancelled) setMonitorId('');
      })
      .finally(() => {
        if (!cancelled) setResolvingMonitorId(false);
      });
    return () => {
      cancelled = true;
    };
  }, [identifierProp, instUuid]);

  const identifier = identifierProp === 'instUuid' ? instUuid : monitorId;
  const canUsePublic = canShowCrossModulePublicWidget({
    hostApp: 'cmdb',
    widgetKey,
    hasOpsAnalysis,
    providerDeclared: widget.declared,
  });
  const { Widget, loadFailed } = useLazyAppWidget({
    loadWidget: widget.loadWidget,
    active: canUsePublic && Boolean(identifier),
  });

  if (widget.status === 'loading' || resolvingMonitorId) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (!canUsePublic) {
    return <CompactEmptyState description={t('common.noData')} />;
  }
  if (!identifier) {
    return <CompactEmptyState description={t('Model.missingStableId')} />;
  }
  if (loadFailed) {
    return <CompactEmptyState description={t('common.loadFailed')} />;
  }
  if (!Widget) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }

  return (
    <div className="h-full min-h-[280px] min-w-0">
      {identifierProp === 'instUuid' ? (
        <InstUuidMount Widget={Widget as InstUuidWidget} instUuid={identifier} />
      ) : (
        <MonitorIdMount Widget={Widget as MonitorIdWidget} monitorId={identifier} />
      )}
    </div>
  );
}

function InstUuidMount({
  Widget,
  instUuid,
}: {
  Widget: InstUuidWidget;
  instUuid: string;
}) {
  return <Widget instUuid={instUuid} />;
}

function MonitorIdMount({
  Widget,
  monitorId,
}: {
  Widget: MonitorIdWidget;
  monitorId: string;
}) {
  return <Widget monitorId={monitorId} />;
}
