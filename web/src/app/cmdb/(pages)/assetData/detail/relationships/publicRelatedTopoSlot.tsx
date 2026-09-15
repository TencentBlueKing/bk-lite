'use client';

import React from 'react';
import { Spin } from 'antd';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import { useAppWidget, useLazyAppWidget } from '@/context/appCapabilities';

type InstUuidWidget = React.ComponentType<{ instUuid: string }>;

export function PublicRelatedTopoSlot({
  instUuid,
  fallback,
}: {
  instUuid: string;
  fallback: React.ReactNode;
}) {
  const widget = useAppWidget('ops-analysis.relatedTopology');
  const resolvedInstUuid = resolveCmdbInstUuid(instUuid) || '';
  const canUsePublic = widget.declared && Boolean(resolvedInstUuid);
  const { Widget, loadFailed } = useLazyAppWidget({
    loadWidget: widget.loadWidget,
    active: canUsePublic,
  });

  if (!resolvedInstUuid) {
    return <>{fallback}</>;
  }
  if (widget.status === 'loading') {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (!canUsePublic || loadFailed) {
    return <>{fallback}</>;
  }
  if (!Widget) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-160px)] min-h-[280px] min-w-0 w-full">
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
