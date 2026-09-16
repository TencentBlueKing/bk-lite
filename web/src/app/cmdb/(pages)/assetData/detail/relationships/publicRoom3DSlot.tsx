'use client';

import React from 'react';
import { Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import {
  canShowCrossModulePublicWidget,
  hasAppAccess,
  useAppWidget,
  useLazyAppWidget,
} from '@/context/appCapabilities';
import { useClientData } from '@/context/client';

type InstUuidWidget = React.ComponentType<{ instUuid: string }>;

export function canShowRoom3DTab(options: {
  modelId: string;
  declared: boolean;
  instUuid: string;
  hasOpsAnalysis: boolean;
}): boolean {
  return (
    options.modelId === 'server_room' &&
    Boolean(resolveCmdbInstUuid(options.instUuid)) &&
    canShowCrossModulePublicWidget({
      hostApp: 'cmdb',
      widgetKey: 'ops-analysis.room3D',
      hasOpsAnalysis: options.hasOpsAnalysis,
      providerDeclared: options.declared,
    })
  );
}

export function PublicRoom3DSlot({ instUuid }: { instUuid: string }) {
  const { t } = useTranslation();
  const { clientData } = useClientData();
  const hasOpsAnalysis = hasAppAccess(clientData, 'ops-analysis');
  const widget = useAppWidget('ops-analysis.room3D');
  const resolvedInstUuid = resolveCmdbInstUuid(instUuid) || '';
  const canUsePublic =
    canShowCrossModulePublicWidget({
      hostApp: 'cmdb',
      widgetKey: 'ops-analysis.room3D',
      hasOpsAnalysis,
      providerDeclared: widget.declared,
    }) && Boolean(resolvedInstUuid);
  const { Widget, loadFailed } = useLazyAppWidget({
    loadWidget: widget.loadWidget,
    active: canUsePublic,
  });

  if (widget.status === 'loading') {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (!resolvedInstUuid) {
    return <CompactEmptyState description={t('Model.missingStableId')} />;
  }
  if (!canUsePublic) {
    return <CompactEmptyState description={t('common.noData')} />;
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
      <InstUuidMount
        Widget={Widget as InstUuidWidget}
        instUuid={resolvedInstUuid}
      />
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
