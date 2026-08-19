'use client';

import React from 'react';
import { Segmented, Select } from 'antd';
import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { isScreenChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import {
  buildScreenContentTokenStyle,
  buildScreenOverlayPopupProps,
} from '@/app/ops-analysis/utils/screenWidgetTokens';
import '@/app/ops-analysis/utils/screenOverlayDropdown.scss';
import styles from './componentParamSwitchControl.module.scss';

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
  const usesScreenTheme = isScreenChartThemeMode(chartThemeMode);
  const screenControlStyle = buildScreenContentTokenStyle(chartThemeMode);
  const screenOverlayPopupProps = buildScreenOverlayPopupProps(chartThemeMode);

  if (!inputConfig || inputConfig.control === 'input' || !options.length || value === undefined) {
    return null;
  }

  if (inputConfig.control === 'radio') {
    return (
      <Segmented
        block={block}
        className={`min-w-max ${styles.control}`}
        style={screenControlStyle}
        options={options}
        value={value}
        onChange={(nextValue) => onChange?.(nextValue as string | number)}
      />
    );
  }

  if (inputConfig.control === 'select') {
    return (
      <Select
        className={`min-w-32 ${styles.control}${usesScreenTheme ? ` ${styles.screenControl}` : ''}`}
        style={screenControlStyle}
        {...screenOverlayPopupProps}
        options={options}
        value={value}
        onChange={(nextValue) => onChange?.(nextValue)}
      />
    );
  }

  return null;
};

export default ComponentParamSwitchControl;
