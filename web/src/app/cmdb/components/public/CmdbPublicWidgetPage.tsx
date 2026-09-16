'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Spin } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import { useAppWidget, useLazyAppWidget } from '@/context/appCapabilities';
import type { AppWidgetKey } from '@/context/appCapabilities';
import { useInstanceApi } from '@/app/cmdb/api';

type InstUuidWidget = React.ComponentType<{ instUuid: string }>;
type MonitorIdWidget = React.ComponentType<{ monitorId: string }>;
type NodeIdWidget = React.ComponentType<{ nodeId: string }>;

export function CmdbPublicWidgetPage({
  widgetKey,
  identifierProp,
}: {
  widgetKey: AppWidgetKey;
  identifierProp: 'instUuid' | 'monitorId' | 'nodeId';
}) {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const instUuid = resolveCmdbInstUuid(searchParams.get('inst_uuid')) || '';
  const widget = useAppWidget(widgetKey);
  const { getInstanceDetail } = useInstanceApi();
  const getInstanceDetailRef = useRef(getInstanceDetail);
  getInstanceDetailRef.current = getInstanceDetail;
  const [monitorId, setMonitorId] = useState('');
  const [nodeId, setNodeId] = useState('');
  const [resolvingIdentifier, setResolvingIdentifier] = useState(
    identifierProp === 'monitorId' || identifierProp === 'nodeId',
  );

  useEffect(() => {
    if (identifierProp === 'instUuid') {
      setResolvingIdentifier(false);
      setMonitorId('');
      setNodeId('');
      return;
    }
    if (!instUuid) {
      setResolvingIdentifier(false);
      setMonitorId('');
      setNodeId('');
      return;
    }
    let cancelled = false;
    setResolvingIdentifier(true);
    getInstanceDetailRef.current(instUuid)
      .then((detail: { monitor_id?: string; node_id?: string }) => {
        if (!cancelled) {
          setMonitorId(String(detail?.monitor_id || '').trim());
          setNodeId(String(detail?.node_id || '').trim());
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMonitorId('');
          setNodeId('');
        }
      })
      .finally(() => {
        if (!cancelled) setResolvingIdentifier(false);
      });
    return () => {
      cancelled = true;
    };
  }, [identifierProp, instUuid]);

  const identifier =
    identifierProp === 'instUuid'
      ? instUuid
      : identifierProp === 'monitorId'
        ? monitorId
        : nodeId;
  // 提供方未购 / 无模块级访问时目录探测不到该键，declared 即为 false。
  const canUsePublic = widget.declared;
  const { Widget, loadFailed } = useLazyAppWidget({
    loadWidget: widget.loadWidget,
    active: canUsePublic && Boolean(identifier),
  });

  if (widget.status === 'loading' || resolvingIdentifier) {
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
      ) : identifierProp === 'monitorId' ? (
        <MonitorIdMount Widget={Widget as MonitorIdWidget} monitorId={identifier} />
      ) : (
        <NodeIdMount Widget={Widget as NodeIdWidget} nodeId={identifier} />
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

function NodeIdMount({
  Widget,
  nodeId,
}: {
  Widget: NodeIdWidget;
  nodeId: string;
}) {
  return <Widget nodeId={nodeId} />;
}
