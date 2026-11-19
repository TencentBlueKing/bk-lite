'use client';

import React, { useEffect, useState } from 'react';
import { Segmented, Select } from 'antd';
import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { isOptionInputControl } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import ScreenWidgetThemeProvider from '@/app/ops-analysis/components/screenWidgetThemeProvider';
import { APP_VIEW_FULLSCREEN_EVENT, isAppViewFullscreenActive } from '@/components/app-view-fullscreen';
import { fullscreenPopupContainer } from '@/utils/fullscreenPopupContainer';
import styles from './componentParamSwitchControl.module.scss';

/** 仪表盘全屏壳是 z-index 1100，下拉层要高过它。筛选条用的是同一档。 */
export const COMPONENT_SWITCH_FULLSCREEN_POPUP_Z_INDEX = 1200;

export const resolveComponentSwitchPopup = (): {
  zIndex?: number;
  getPopupContainer?: () => HTMLElement;
} => {
  if (typeof document === 'undefined') {
    return {};
  }
  const browserFullscreen = document.fullscreenElement instanceof HTMLElement;
  if (!browserFullscreen && !isAppViewFullscreenActive()) {
    return {};
  }
  return {
    zIndex: COMPONENT_SWITCH_FULLSCREEN_POPUP_Z_INDEX,
    getPopupContainer: browserFullscreen ? fullscreenPopupContainer : undefined,
  };
};

interface ComponentParamSwitchControlProps {
  inputConfig?: InputControlConfig;
  options: InputOption[];
  value?: string | number | Array<string | number>;
  onChange?: (value: string | number | Array<string | number>) => void;
  block?: boolean;
  chartThemeMode?: OpsChartThemeMode;
  /** 与表格、排行文字同一套屏幕缩放。1 表示按设计像素。 */
  scale?: number;
}

const ComponentParamSwitchControl: React.FC<ComponentParamSwitchControlProps> = ({
  inputConfig,
  options,
  value,
  onChange,
  block = false,
  chartThemeMode,
  scale = 1,
}) => {
  const [popupLayer, setPopupLayer] = useState(resolveComponentSwitchPopup);

  useEffect(() => {
    const sync = () => setPopupLayer(resolveComponentSwitchPopup());
    window.addEventListener(APP_VIEW_FULLSCREEN_EVENT, sync);
    document.addEventListener('fullscreenchange', sync);
    return () => {
      window.removeEventListener(APP_VIEW_FULLSCREEN_EVENT, sync);
      document.removeEventListener('fullscreenchange', sync);
    };
  }, []);

  if (!isOptionInputControl(inputConfig) || !options.length) {
    return null;
  }
  const multiple = Boolean(inputConfig.multiple);

  const resolvedScale = Number.isFinite(scale) && scale > 0 ? scale : 1;
  const fontSize = Math.round(13 * resolvedScale);
  const height = Math.round(28 * resolvedScale);
  const switchStyle = {
    '--ops-switch-font': `${fontSize}px`,
    '--ops-switch-height': `${height}px`,
    '--ops-switch-pad': `${Math.round(12 * resolvedScale)}px`,
    '--ops-switch-select': `${Math.round(128 * resolvedScale)}px`,
  } as React.CSSProperties;

  let control: React.ReactNode = null;
  if (multiple) {
    const selected = Array.isArray(value)
      ? value
      : (typeof value === 'string' || typeof value === 'number' ? [value] : []);
    control = (
      <Select
        mode="multiple"
        maxTagCount="responsive"
        maxCount={inputConfig.maxCount}
        style={{ height, fontSize, width: '100%', maxWidth: Math.round(220 * resolvedScale) }}
        styles={popupLayer.zIndex ? { popup: { root: { zIndex: popupLayer.zIndex } } } : undefined}
        getPopupContainer={popupLayer.getPopupContainer}
        options={options}
        value={selected}
        onChange={(nextValue) => onChange?.(nextValue)}
      />
    );
  } else if (inputConfig.control === 'radio') {
    control = (
      <Segmented
        block={block}
        options={options.map((option) => ({
          value: option.value,
          label: (
            <span className={styles.optionLabel} title={option.label}>
              {option.label}
            </span>
          ),
        }))}
        value={typeof value === 'string' || typeof value === 'number' ? value : undefined}
        onChange={(nextValue) => onChange?.(nextValue as string | number)}
      />
    );
  } else if (inputConfig.control === 'select') {
    control = (
      <Select
        style={{ height, fontSize }}
        styles={popupLayer.zIndex ? { popup: { root: { zIndex: popupLayer.zIndex } } } : undefined}
        getPopupContainer={popupLayer.getPopupContainer}
        options={options}
        value={typeof value === 'string' || typeof value === 'number' ? value : undefined}
        onChange={(nextValue) => onChange?.(nextValue)}
      />
    );
  }

  if (!control) {
    return null;
  }

  return (
    <ScreenWidgetThemeProvider mode={chartThemeMode} className="block w-max max-w-full min-w-0">
      <div className={styles.root} style={switchStyle}>
        {control}
      </div>
    </ScreenWidgetThemeProvider>
  );
};

export default ComponentParamSwitchControl;
