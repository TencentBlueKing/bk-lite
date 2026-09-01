'use client';

import React from 'react';
import { Segmented } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  APP_TOPO_EXPAND_DEPTH_OPTIONS,
  parseAppTopoExpandDepth,
  type AppTopoExpandDepth,
} from './expandDepth';

interface ExpandDepthControlProps {
  value: AppTopoExpandDepth;
  onChange: (depth: AppTopoExpandDepth) => void;
}

const ExpandDepthControl: React.FC<ExpandDepthControlProps> = ({
  value,
  onChange,
}) => {
  const { t } = useTranslation();
  return (
    <div className="flex shrink-0 items-center gap-2">
      <span className="whitespace-nowrap text-[13px] text-[var(--color-text-3)]">
        {t('ApplicationResourceOverview.expandDepthLabel')}
      </span>
      <Segmented
        size="small"
        value={value}
        aria-label={t('ApplicationResourceOverview.expandDepthLabel')}
        options={APP_TOPO_EXPAND_DEPTH_OPTIONS.map((depth) => ({
          label: t('ApplicationResourceOverview.expandDepthOption', '{n}层', {
            n: depth,
          }),
          value: depth,
        }))}
        onChange={(next) => onChange(parseAppTopoExpandDepth(next))}
      />
    </div>
  );
};

export default ExpandDepthControl;
