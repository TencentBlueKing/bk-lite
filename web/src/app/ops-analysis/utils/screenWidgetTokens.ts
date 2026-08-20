import type { CSSProperties } from 'react';
import { theme as antdTheme } from 'antd';
import type { ThemeConfig } from 'antd/es/config-provider/context';
import type { SemanticColorTokens } from '@/theme';
import {
  getOpsChartThemeByMode,
  isScreenChartThemeMode,
  type OpsChartThemeMode,
} from '@/app/ops-analysis/utils/chartTheme';

export const SCREEN_ANTD_CSS_VAR_KEY = {
  'screen-dark': 'ops-screen-dark',
  'screen-light': 'ops-screen-light',
} as const;

/** 控件实心底与选中面；与画布玻璃面区分，保证 Select/Segmented 可读。 */
const SCREEN_CONTROL_TOKENS = {
  'screen-dark': {
    containerBg: '#14243a',
    elevatedBg: '#14243a',
    border: 'rgba(112, 147, 195, 0.16)',
    text: 'rgba(226, 232, 240, 0.84)',
    selectedBg: 'rgba(59, 130, 246, 0.2)',
  },
  'screen-light': {
    containerBg: 'rgba(255, 255, 255, 0.42)',
    elevatedBg: 'rgba(255, 255, 255, 0.96)',
    border: 'rgba(121, 145, 176, 0.18)',
    text: '#34445b',
    selectedBg: '#e7effd',
  },
} as const;

const resolveHoverBg = (mode: 'screen-dark' | 'screen-light') => {
  const theme = getOpsChartThemeByMode(mode);
  // 亮色大屏图例/选中面用实心浅蓝，暗色跟 legendHover
  return mode === 'screen-light'
    ? SCREEN_CONTROL_TOKENS[mode].selectedBg
    : theme.legendHoverBg;
};

/** 大屏下把仪表盘语义 token 改写成 screen 主题色，子树里的 --color-* 会跟着变。 */
export const buildScreenContentTokenStyle = (
  mode?: OpsChartThemeMode,
): CSSProperties | undefined => {
  if (!isScreenChartThemeMode(mode)) {
    return undefined;
  }

  const theme = getOpsChartThemeByMode(mode);
  const hoverBg = resolveHoverBg(mode);
  return {
    '--color-text-1': theme.panelTitleColor,
    '--color-text-2': theme.panelDescriptionColor,
    '--color-text-3': theme.singleValueMetaColor,
    '--color-text-4': theme.singleValueMetaColor,
    '--color-bg': theme.panelSubtleBg,
    '--color-bg-1': theme.panelBg,
    '--color-bg-2': theme.panelBg,
    '--color-fill-1': theme.panelSubtleBg,
    '--color-fill-2': hoverBg,
    '--color-fill-3': theme.legendRowBg,
    '--color-border': theme.panelBorderColor,
    '--color-border-1': theme.panelBorderColor,
    '--color-border-2': theme.panelBorderColor,
    '--color-border-3': theme.panelBorderColor,
    '--color-primary-bg-active': hoverBg,
  } as CSSProperties;
};

/** 大屏组件子树的 Ant Design 主题；非大屏 mode 返回 undefined。 */
export const createScreenAntdTheme = (
  mode: OpsChartThemeMode | undefined,
  systemTokens: SemanticColorTokens,
): ThemeConfig | undefined => {
  if (!isScreenChartThemeMode(mode)) {
    return undefined;
  }

  const theme = getOpsChartThemeByMode(mode);
  const control = SCREEN_CONTROL_TOKENS[mode];
  const hoverBg = resolveHoverBg(mode);

  return {
    cssVar: { key: SCREEN_ANTD_CSS_VAR_KEY[mode] },
    algorithm:
      mode === 'screen-dark'
        ? antdTheme.darkAlgorithm
        : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: systemTokens.interactionPrimary,
      colorSuccess: systemTokens.statusSuccess,
      colorWarning: systemTokens.statusWarning,
      colorInfo: systemTokens.statusInfo,
      colorError: systemTokens.statusError,
      colorBgLayout: theme.panelSubtleBg,
      // 触发器实心底，避免玻璃面板上 Input/Select 发白或发虚
      colorBgContainer: control.containerBg,
      colorBgElevated: control.elevatedBg,
      colorFillSecondary: hoverBg,
      colorFillTertiary: hoverBg,
      colorText: theme.panelTitleColor,
      colorTextSecondary: theme.panelDescriptionColor,
      colorTextPlaceholder: theme.singleValueMetaColor,
      colorTextQuaternary: theme.singleValueMetaColor,
      colorBorder: control.border,
      colorBorderSecondary: theme.panelBorderColor,
      colorIcon: theme.singleValueMetaColor,
    },
    components: {
      Segmented: {
        trackBg: control.containerBg,
        itemColor: control.text,
        itemHoverColor: theme.panelTitleColor,
        itemHoverBg: hoverBg,
        itemSelectedBg: control.selectedBg,
        itemSelectedColor: theme.panelTitleColor,
        itemActiveBg: control.selectedBg,
      },
      Select: {
        colorBgContainer: control.containerBg,
        colorBorder: control.border,
        optionSelectedBg: control.selectedBg,
        optionActiveBg: hoverBg,
      },
      Input: {
        colorBgContainer: control.containerBg,
        colorBorder: control.border,
      },
      DatePicker: {
        colorBgContainer: control.containerBg,
        colorBorder: control.border,
      },
    },
  };
};
