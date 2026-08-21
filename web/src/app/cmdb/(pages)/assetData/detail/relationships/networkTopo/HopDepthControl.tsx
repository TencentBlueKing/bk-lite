'use client';

import React from 'react';
import { Segmented } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  NETWORK_TOPO_HOP_OPTIONS,
  parseNetworkTopoHop,
  type NetworkTopoHop,
} from './hopDepth';

interface HopDepthControlProps {
  value: NetworkTopoHop;
  onChange: (hop: NetworkTopoHop) => void;
}

const HOP_LABEL_KEYS = {
  1: 'Model.networkTopoHopOne',
  2: 'Model.networkTopoHopTwo',
  3: 'Model.networkTopoHopThree',
} as const;

const HopDepthControl: React.FC<HopDepthControlProps> = ({ value, onChange }) => {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 shrink-0">
      <span className="text-[13px] text-[var(--color-text-3)] whitespace-nowrap">
        {t('Model.networkTopoHopLabel')}
      </span>
      <Segmented
        size="small"
        value={value}
        aria-label={t('Model.networkTopoHopLabel')}
        options={NETWORK_TOPO_HOP_OPTIONS.map((hop) => ({
          label: t(HOP_LABEL_KEYS[hop]),
          value: hop,
        }))}
        onChange={(next) => onChange(parseNetworkTopoHop(next))}
      />
    </div>
  );
};

export default HopDepthControl;
