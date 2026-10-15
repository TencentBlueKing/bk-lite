'use client';

import React from 'react';
import { Select, Tooltip } from 'antd';
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
  const label = t('ApplicationResourceOverview.expandDepthLabel');
  return (
    <Tooltip title={label}>
      <Select
        size="small"
        value={value}
        aria-label={label}
        popupMatchSelectWidth={false}
        style={{ width: 72 }}
        options={APP_TOPO_EXPAND_DEPTH_OPTIONS.map((depth) => ({
          label: t('ApplicationResourceOverview.expandDepthOption', '{n}层', {
            n: depth,
          }),
          value: depth,
        }))}
        onChange={(next) => onChange(parseAppTopoExpandDepth(next))}
      />
    </Tooltip>
  );
};

export default ExpandDepthControl;
