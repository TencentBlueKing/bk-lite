'use client';

import React from 'react';
import { Segmented } from 'antd';
import type {
  RuntimeParamControl,
  RuntimeParamValue,
} from '@/app/ops-analysis/types/dashBoard';
import {
  getRuntimeParamSegmentedOptions,
  hasRuntimeParamSegmentedValue,
} from '@/app/ops-analysis/utils/runtimeParamControl';

interface RuntimeParamSegmentedProps {
  control?: RuntimeParamControl;
  value?: RuntimeParamValue;
  onChange?: (value: RuntimeParamValue) => void;
  block?: boolean;
}

const RuntimeParamSegmented: React.FC<RuntimeParamSegmentedProps> = ({
  control,
  value,
  onChange,
  block = false,
}) => {
  const options = getRuntimeParamSegmentedOptions(control);
  if (!options.length || !hasRuntimeParamSegmentedValue(control, value)) {
    return null;
  }

  return (
    <Segmented
      block={block}
      className="min-w-max"
      options={options}
      value={value}
      onChange={(nextValue) => onChange?.(nextValue as RuntimeParamValue)}
    />
  );
};

export default RuntimeParamSegmented;
