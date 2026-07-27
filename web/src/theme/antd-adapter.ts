import { theme as antdTheme } from 'antd';
import type { ThemeConfig } from 'antd/es/config-provider/context';
import type { SemanticColorTokens, ThemeMode } from './contract';

export const createAntdTheme = (
  mode: ThemeMode,
  tokens: SemanticColorTokens
): ThemeConfig => ({
  cssVar: true,
  algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
  token: {
    colorPrimary: tokens.interactionPrimary,
    colorBgLayout: tokens.surfacePage,
    colorBgContainer: tokens.surfaceContainer,
    colorText: tokens.textPrimary,
    colorTextSecondary: tokens.textSecondary,
    colorBorder: tokens.borderDefault,
    colorSuccess: tokens.statusSuccess,
    colorWarning: tokens.statusWarning,
    colorInfo: tokens.statusInfo,
    colorError: tokens.statusError,
  },
  components: {
    Menu: {
      itemBg: tokens.sideNavigationBackground,
      itemColor: tokens.sideNavigationText,
      itemHoverBg: tokens.sideNavigationHoverBackground,
      itemSelectedBg: tokens.sideNavigationActiveBackground,
      itemSelectedColor: tokens.sideNavigationActiveText,
    },
  },
});
