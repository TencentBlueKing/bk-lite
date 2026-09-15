'use client';

import React from 'react';
import { Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import { useAppWidget, useLazyAppWidget } from '@/context/appCapabilities';

type InstUuidWidget = React.ComponentType<{ instUuid: string }>;

export function canShowNetworkStatusTopoTab(options: {
  hasNetworkTheme: boolean;
  declared: boolean;
  instUuid: string;
}): boolean {
  return (
    options.hasNetworkTheme &&
    options.declared &&
    Boolean(resolveCmdbInstUuid(options.instUuid))
  );
}

export function PublicNetworkStatusTopoSlot({
  instUuid,
}: {
  instUuid: string;
}) {
  const { t } = useTranslation();
  const widget = useAppWidget('ops-analysis.networkStatusTopology');
  const resolvedInstUuid = resolveCmdbInstUuid(instUuid) || '';
  const canUsePublic = widget.declared && Boolean(resolvedInstUuid);
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
  if (!widget.declared) {
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
