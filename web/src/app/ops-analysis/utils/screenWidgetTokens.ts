import type { CSSProperties } from 'react';
import {
  getOpsChartThemeByMode,
  isScreenChartThemeMode,
  type OpsChartThemeMode,
} from '@/app/ops-analysis/utils/chartTheme';

export const SCREEN_SWITCH_DROPDOWN_CLASS = 'screen-component-switch-dropdown';

const SCREEN_SWITCH_TOKENS = {
  'screen-dark': {
    bg: '#14243a',
    dropdownBg: '#14243a',
    border: 'rgba(112, 147, 195, 0.16)',
    dropdownBorder: 'rgba(112, 147, 195, 0.28)',
    color: 'rgba(226, 232, 240, 0.84)',
    selectedBg: 'rgba(59, 130, 246, 0.2)',
    dropdownShadow: '0 10px 24px rgba(0, 10, 24, 0.36)',
  },
  'screen-light': {
    bg: 'rgba(255, 255, 255, 0.42)',
    dropdownBg: 'rgba(255, 255, 255, 0.96)',
    border: 'rgba(121, 145, 176, 0.18)',
    dropdownBorder: 'rgba(121, 145, 176, 0.22)',
    color: '#34445b',
    selectedBg: '#e7effd',
    dropdownShadow: '0 10px 24px rgba(31, 47, 70, 0.12)',
  },
} as const;

/** 大屏下把仪表盘语义 token 改写成 screen 主题色，子树里的 --color-* 会跟着变。 */
export const buildScreenContentTokenStyle = (
  mode?: OpsChartThemeMode,
): CSSProperties | undefined => {
  if (!isScreenChartThemeMode(mode)) {
    return undefined;
  }

  const theme = getOpsChartThemeByMode(mode);
  const switchTokens = SCREEN_SWITCH_TOKENS[mode];
  return {
    '--color-text-1': theme.panelTitleColor,
    '--color-text-2': theme.panelDescriptionColor,
    '--color-text-3': theme.singleValueMetaColor,
    '--color-bg': theme.panelSubtleBg,
    '--color-bg-1': theme.panelBg,
    '--color-primary-bg-active': theme.legendHoverBg,
    '--chart-legend-hover-bg':
      mode === 'screen-light' ? switchTokens.selectedBg : theme.legendHoverBg,
    '--screen-component-switch-bg': switchTokens.bg,
    '--screen-component-switch-border': switchTokens.border,
    '--screen-component-switch-color': switchTokens.color,
    '--screen-component-switch-hover-bg': theme.legendHoverBg,
    '--screen-component-switch-hover-color': theme.panelTitleColor,
    '--screen-component-switch-selected-bg': switchTokens.selectedBg,
    '--screen-component-switch-selected-color': theme.panelTitleColor,
  } as CSSProperties;
};

/** 下拉挂到 body 后继承不到画布变量，把大屏色写到 popup 根节点上。 */
export const buildScreenSwitchDropdownStyle = (
  mode?: OpsChartThemeMode,
): CSSProperties | undefined => {
  if (!isScreenChartThemeMode(mode)) {
    return undefined;
  }

  const theme = getOpsChartThemeByMode(mode);
  const switchTokens = SCREEN_SWITCH_TOKENS[mode];
  return {
    '--screen-switch-dropdown-bg': switchTokens.dropdownBg,
    '--screen-switch-dropdown-border': switchTokens.dropdownBorder,
    '--screen-switch-dropdown-shadow': switchTokens.dropdownShadow,
    '--screen-switch-dropdown-color': switchTokens.color,
    '--screen-switch-dropdown-hover-bg': theme.legendHoverBg,
    '--screen-switch-dropdown-hover-color': theme.panelTitleColor,
    '--screen-switch-dropdown-selected-bg': switchTokens.selectedBg,
    '--screen-switch-dropdown-selected-color': theme.panelTitleColor,
  } as CSSProperties;
};

export const buildScreenOverlayPopupProps = (mode?: OpsChartThemeMode) => {
  const dropdownStyle = buildScreenSwitchDropdownStyle(mode);
  if (!dropdownStyle) {
    return undefined;
  }

  return {
    classNames: { popup: { root: SCREEN_SWITCH_DROPDOWN_CLASS } },
    styles: { popup: { root: dropdownStyle } },
  };
};
