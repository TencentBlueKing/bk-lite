'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Select, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useAppCapability } from '@/context/appCapabilities';
import type { MonitorObjectSnapshot } from '@/app/alarm/types/alarms';
import {
  listRelatedTopologyCenters,
  resolveRelatedTopologyTabVisibility,
  type RelatedTopologyCenter,
} from '@/app/alarm/utils/relatedTopologyCenters';

type WidgetComponent = React.ComponentType<{ instUuid: string }>;

export function useRelatedTopologyTab(monitorObjects?: MonitorObjectSnapshot[]) {
  const capability = useAppCapability('ops-analysis');
  const Widget =
    capability.status === 'ready'
      ? capability.api.RelatedTopologyWidget
      : null;
  const declared = typeof Widget === 'function';
  const centers = useMemo(
    () => listRelatedTopologyCenters(monitorObjects),
    [monitorObjects],
  );

  return {
    visible: resolveRelatedTopologyTabVisibility({
      declared,
      centerCount: centers.length,
    }),
    centers,
    Widget,
  };
}

export function RelatedTopologyTabContent({
  centers,
  Widget,
}: {
  centers: RelatedTopologyCenter[];
  Widget: WidgetComponent | null;
}) {
  const { t } = useTranslation();
  const [instUuid, setInstUuid] = useState(centers[0]?.instUuid || '');
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => {
    if (!centers.some((center) => center.instUuid === instUuid)) {
      setInstUuid(centers[0]?.instUuid || '');
    }
  }, [centers, instUuid]);

  if (!instUuid) {
    return null;
  }

  return (
    <div className="flex h-[min(520px,calc(100vh-360px))] min-h-[280px] min-w-0 flex-col gap-4">
      <div className="flex items-center gap-2">
        {centers.length > 1 && (
          <Select
            className="w-[240px]"
            value={instUuid}
            options={centers.map((center) => ({
              value: center.instUuid,
              label: center.label,
            }))}
            onChange={setInstUuid}
          />
        )}
        <Button
          type="text"
          className="ml-auto"
          aria-label={t('common.refresh')}
          icon={<ReloadOutlined />}
          onClick={() => setRefreshNonce((current) => current + 1)}
        />
      </div>
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        {Widget ? (
          <Widget key={`${instUuid}:${refreshNonce}`} instUuid={instUuid} />
        ) : (
          <div className="flex h-full items-center justify-center overflow-hidden rounded-lg bg-[var(--color-fill-1)]">
            <Spin />
          </div>
        )}
      </div>
    </div>
  );
}

export function relatedTopologyTabItem(
  t: (id: string) => string,
  visible: boolean,
) {
  if (!visible) {
    return null;
  }
  return {
    key: 'relatedTopology',
    label: t('alarms.relatedTopology'),
  };
}
