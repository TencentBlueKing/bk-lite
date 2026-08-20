'use client';

import React from 'react';
import { Segmented, Select } from 'antd';
import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import ScreenWidgetThemeProvider from '@/app/ops-analysis/components/screenWidgetThemeProvider';

interface ComponentParamSwitchControlProps {
  inputConfig?: InputControlConfig;
  options: InputOption[];
  value?: string | number;
  onChange?: (value: string | number) => void;
  block?: boolean;
  chartThemeMode?: OpsChartThemeMode;
}

const ComponentParamSwitchControl: React.FC<ComponentParamSwitchControlProps> = ({
  inputConfig,
  options,
  value,
  onChange,
  block = false,
  chartThemeMode,
}) => {
  if (!inputConfig || inputConfig.control === 'input' || !options.length || value === undefined) {
    return null;
  }

  let control: React.ReactNode = null;
  if (inputConfig.control === 'radio') {
    control = (
      <Segmented
        block={block}
        className="min-w-max"
        options={options}
        value={value}
        onChange={(nextValue) => onChange?.(nextValue as string | number)}
      />
    );
  } else if (inputConfig.control === 'select') {
    control = (
      <Select
        className="min-w-32"
        options={options}
        value={value}
        onChange={(nextValue) => onChange?.(nextValue)}
      />
    );
  }

  if (!control) {
    return null;
  }

  return (
    <ScreenWidgetThemeProvider mode={chartThemeMode} className="inline-flex min-w-0">
      {control}
    </ScreenWidgetThemeProvider>
  );
};

export default ComponentParamSwitchControl;
