'use client';

import React, { useMemo } from 'react';
import NetworkStatusTopology from '@/app/ops-analysis/components/widgets/networkStatusTopology';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';

export interface NetworkStatusTopologyEmbedProps {
  instUuid: string;
}

const NetworkStatusTopologyEmbed = ({
  instUuid,
}: NetworkStatusTopologyEmbedProps) => {
  const config = useMemo<ValueConfig>(
    () => ({
      chartType: 'networkStatusTopology',
      sceneWidgetType: 'networkStatusTopology',
      networkStatusTopology: {
        instUuids: instUuid ? [instUuid] : [],
        instUuid: instUuid || undefined,
        oneHop: true,
        nodeLimit: 100,
      },
    }),
    [instUuid],
  );

  return (
    <div className="h-full min-h-[280px] min-w-0">
      <NetworkStatusTopology
        config={config}
        layoutEditable={false}
      />
    </div>
  );
};

export default NetworkStatusTopologyEmbed;
