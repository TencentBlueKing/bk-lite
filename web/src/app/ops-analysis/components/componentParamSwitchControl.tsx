'use client';

import React from 'react';
import { Segmented, Select } from 'antd';
import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';

interface ComponentParamSwitchControlProps {
  inputConfig?: InputControlConfig;
  options: InputOption[];
  value?: string | number;
  onChange?: (value: string | number) => void;
  block?: boolean;
}

const ComponentParamSwitchControl: React.FC<ComponentParamSwitchControlProps> = ({
  inputConfig,
  options,
  value,
  onChange,
  block = false,
}) => {
  if (!inputConfig || inputConfig.control === 'input' || !options.length || value === undefined) {
    return null;
  }

  if (inputConfig.control === 'radio') {
    return (
      <Segmented
        block={block}
        className="min-w-max"
        options={options}
        value={value}
        onChange={(nextValue) => onChange?.(nextValue as string | number)}
      />
    );
  }

  if (inputConfig.control === 'select') {
    return (
      <Select
        className="min-w-32"
        options={options}
        value={value}
        onChange={(nextValue) => onChange?.(nextValue)}
      />
    );
  }

  return null;
};

export default ComponentParamSwitchControl;
