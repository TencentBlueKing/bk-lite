'use client';

import React, { useEffect, useState } from 'react';
import { Segmented, Select } from 'antd';
import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import type { ScreenLayoutMode } from '@/app/ops-analysis/types/dashBoard';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { isOptionInputControl } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import ScreenWidgetThemeProvider from '@/app/ops-analysis/components/screenWidgetThemeProvider';
import { APP_VIEW_FULLSCREEN_EVENT, isAppViewFullscreenActive } from '@/components/app-view-fullscreen';
import { fullscreenPopupContainer } from '@/utils/fullscreenPopupContainer';
import styles from './componentParamSwitchControl.module.scss';

/** 仪表盘全屏壳是 z-index 1100，下拉层要高过它。筛选条用的是同一档。 */
export const COMPONENT_SWITCH_FULLSCREEN_POPUP_Z_INDEX = 1200;

/** 下拉项设计字号。菜单挂在画布外面，要按屏幕密度写成屏幕像素。 */
export const COMPONENT_SWITCH_POPUP_FONT_PX = 13;
/** 屏幕再小，选项也不能低于这个字号。 */
export const COMPONENT_SWITCH_POPUP_FONT_FLOOR_PX = 12;

/**
 * 大屏下拉字号跟屏幕密度走，不跟单个组件的宽高走。
 * 密度已经按屏幕相对 1440×810 算出；这里再守住最小字号。
 * 不在大屏上时不改，菜单继续用组件库默认字号。
 */
export const resolveComponentSwitchPopupFont = (
  screenDensity?: number,
): number | undefined => {
  if (typeof screenDensity !== 'number' || !Number.isFinite(screenDensity) || screenDensity <= 0) {
    return undefined;
  }
  return Math.max(
    COMPONENT_SWITCH_POPUP_FONT_FLOOR_PX,
    Math.round(COMPONENT_SWITCH_POPUP_FONT_PX * screenDensity),
  );
};

/**
 * 输入框和下拉菜单用同一套屏幕字号。
 * 菜单在画布外，直接写屏幕像素。
 * 设计画布里输入框还要被外层 transform 再乘一次，所以先除掉 fitScale。
 * 视口像素没有这层 transform。拿不到 fitScale 时无法除掉，保持屏幕像素。
 */
export const resolveComponentSwitchTriggerFont = (
  screenDensity?: number,
  layoutMode?: ScreenLayoutMode,
  fitScale?: number,
): number | undefined => {
  const visualFont = resolveComponentSwitchPopupFont(screenDensity);
  if (visualFont == null) return undefined;
  const insideCanvasTransform = layoutMode !== 'viewportPixels';
  if (
    insideCanvasTransform
    && typeof fitScale === 'number'
    && Number.isFinite(fitScale)
    && fitScale > 0
  ) {
    return visualFont / fitScale;
  }
  return visualFont;
};

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
  /**
   * 大屏相对参考屏幕的密度。输入框和下拉菜单共用。
   * 不传表示不在大屏上。
   */
  screenDensity?: number;
  /** 缺省按设计画布处理：输入框字号要先除掉 fitScale。 */
  layoutMode?: ScreenLayoutMode;
  fitScale?: number;
}

const ComponentParamSwitchControl: React.FC<ComponentParamSwitchControlProps> = ({
  inputConfig,
  options,
  value,
  onChange,
  block = false,
  chartThemeMode,
  scale = 1,
  screenDensity,
  layoutMode,
  fitScale,
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
  const popupFontPx = resolveComponentSwitchPopupFont(screenDensity);
  const triggerFontPx = resolveComponentSwitchTriggerFont(screenDensity, layoutMode, fitScale);
  const popupStyle: React.CSSProperties = {};
  if (popupLayer.zIndex) popupStyle.zIndex = popupLayer.zIndex;
  if (popupFontPx != null) popupStyle.fontSize = popupFontPx;
  const selectPopup = Object.keys(popupStyle).length
    ? { popup: { root: popupStyle } }
    : undefined;

  const resolvedScale = Number.isFinite(scale) && scale > 0 ? scale : 1;
  const fontSize = Math.round(13 * resolvedScale);
  const selectStyle = (extra?: React.CSSProperties): React.CSSProperties => {
    const style = { ...extra };
    if (triggerFontPx != null) style.fontSize = triggerFontPx;
    return style;
  };
  const height = Math.round(28 * resolvedScale);
  const switchStyle = {
    '--ops-switch-font': `${fontSize}px`,
    '--ops-switch-height': `${height}px`,
    '--ops-switch-pad': `${Math.round(12 * resolvedScale)}px`,
    '--ops-switch-select': `${Math.round(128 * resolvedScale)}px`,
    '--ops-switch-select-multiple': `${Math.round(200 * resolvedScale)}px`,
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
        style={selectStyle()}
        styles={selectPopup}
        classNames={popupFontPx != null ? { popup: { root: styles.screenPopup } } : undefined}
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
        style={selectStyle({ height })}
        styles={selectPopup}
        classNames={popupFontPx != null ? { popup: { root: styles.screenPopup } } : undefined}
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
