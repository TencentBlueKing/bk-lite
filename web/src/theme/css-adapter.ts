import type { ResolvedTheme, SemanticColorTokens, ThemeMode } from './contract';

const cssVariableMap = {
  interactionPrimary: '--theme-color-interaction-primary',
  interactionPrimarySoft: '--theme-color-interaction-primary-soft',
  interactionPrimaryActiveBackground: '--theme-color-interaction-primary-active-bg',
  interactionPrimaryBackground: '--theme-color-interaction-primary-bg',
  textPrimary: '--theme-color-text-primary',
  textSecondary: '--theme-color-text-secondary',
  textTertiary: '--theme-color-text-tertiary',
  textDisabled: '--theme-color-text-disabled',
  textActive: '--theme-color-text-active',
  textHoverBackground: '--theme-color-text-hover-bg',
  surfacePage: '--theme-color-surface-page',
  surfaceContainer: '--theme-color-surface-container',
  surfaceHover: '--theme-color-surface-hover',
  surfaceMuted: '--theme-color-surface-muted',
  surfaceLevel1: '--theme-color-surface-level-1',
  surfaceLevel2: '--theme-color-surface-level-2',
  surfaceLevel3: '--theme-color-surface-level-3',
  surfaceLevel4: '--theme-color-surface-level-4',
  surfaceLevel5: '--theme-color-surface-level-5',
  surfaceTranslucent: '--theme-color-surface-translucent',
  surfaceTranslucentSubtle: '--theme-color-surface-translucent-subtle',
  borderDefault: '--theme-color-border-default',
  borderSubtle: '--theme-color-border-subtle',
  borderMuted: '--theme-color-border-muted',
  borderStrong: '--theme-color-border-strong',
  borderEmphasis: '--theme-color-border-emphasis',
  fillSubtle: '--theme-color-fill-subtle',
  fillMuted: '--theme-color-fill-muted',
  fillDefault: '--theme-color-fill-default',
  fillStrong: '--theme-color-fill-strong',
  fillEmphasis: '--theme-color-fill-emphasis',
  statusSuccess: '--theme-color-status-success',
  statusWarning: '--theme-color-status-warning',
  statusInfo: '--theme-color-status-info',
  statusError: '--theme-color-status-error',
  navigationButtonText: '--theme-color-nav-button-text',
  navigationButtonActiveText: '--theme-color-nav-button-active-text',
  navigationButtonBackground: '--theme-color-nav-button-bg',
  navigationButtonActiveBackground: '--theme-color-nav-button-active-bg',
  navigationButtonHoverBackground: '--theme-color-nav-button-hover-bg',
  navigationBorder: '--theme-color-nav-border',
  sideNavigationText: '--theme-color-side-nav-text',
  sideNavigationActiveText: '--theme-color-side-nav-active-text',
  sideNavigationActiveBackground: '--theme-color-side-nav-active-bg',
  sideNavigationHoverBackground: '--theme-color-side-nav-hover-bg',
  sideNavigationBackground: '--theme-color-side-nav-bg',
  modalHeaderBackground: '--theme-color-modal-header-bg',
  imageGradientStart: '--theme-color-image-gradient-start',
  imageGradientEnd: '--theme-color-image-gradient-end',
  portalCardShadow: '--theme-color-portal-card-shadow',
  portalSurfaceSoft: '--theme-color-portal-surface-soft',
  portalSurfaceSofter: '--theme-color-portal-surface-softer',
  portalSurfaceOverlay: '--theme-color-portal-surface-overlay',
  portalPreviewBorder: '--theme-color-portal-preview-border',
  portalPreviewBorderStrong: '--theme-color-portal-preview-border-strong',
  portalPreviewDivider: '--theme-color-portal-preview-divider',
  portalPreviewShell: '--theme-color-portal-preview-shell',
  portalPreviewTabBackground: '--theme-color-portal-preview-tab-bg',
  portalPreviewIconBackground: '--theme-color-portal-preview-icon-bg',
  chartAxisLine: '--theme-color-chart-axis-line',
  chartSplitLine: '--theme-color-chart-split-line',
  chartAxisLabel: '--theme-color-chart-axis-label',
  chartBackground: '--theme-color-chart-background',
  chartTooltipBackground: '--theme-color-chart-tooltip-background',
  chartTooltipBorder: '--theme-color-chart-tooltip-border',
  chartTextPrimary: '--theme-color-chart-text-primary',
  chartTextSecondary: '--theme-color-chart-text-secondary',
  chartTextTertiary: '--theme-color-chart-text-tertiary',
  chartPrimary: '--theme-color-chart-primary',
  chartSuccess: '--theme-color-chart-success',
  chartWarning: '--theme-color-chart-warning',
  chartError: '--theme-color-chart-error',
} satisfies Record<keyof SemanticColorTokens, `--${string}`>;

const legacyVariableMap: Record<string, keyof SemanticColorTokens> = {
  '--color-primary': 'interactionPrimary',
  '--color-primary-bg-active': 'interactionPrimarySoft',
  '--color-secondary': 'surfacePage',
  '--color-text-1': 'textPrimary',
  '--color-text-2': 'textSecondary',
  '--color-text-3': 'textTertiary',
  '--color-text-4': 'textDisabled',
  '--color-text-active': 'textActive',
  '--color-text-hover': 'textHoverBackground',
  '--color-bg': 'surfaceContainer',
  '--color-bg-hover': 'surfaceHover',
  '--color-bg-active': 'interactionPrimaryActiveBackground',
  '--color-border': 'borderDefault',
  '--color-border-1': 'borderSubtle',
  '--color-border-2': 'borderMuted',
  '--color-border-3': 'borderStrong',
  '--color-border-4': 'borderEmphasis',
  '--color-fill-1': 'fillSubtle',
  '--color-fill-2': 'fillMuted',
  '--color-fill-3': 'fillDefault',
  '--color-fill-4': 'fillStrong',
  '--color-fill-5': 'fillEmphasis',
  '--color-bg-1': 'surfaceLevel1',
  '--color-bg-2': 'surfaceLevel2',
  '--color-bg-3': 'surfaceLevel3',
  '--color-bg-4': 'surfaceLevel4',
  '--color-bg-5': 'surfaceLevel5',
  '--color-bg-6': 'surfaceTranslucent',
  '--color-bg-7': 'surfaceTranslucentSubtle',
  '--color-success': 'statusSuccess',
  '--color-fail': 'statusError',
  '--color-background-body': 'surfacePage',
  '--color-components-nav-button-text': 'navigationButtonText',
  '--color-components-nav-button-text-active': 'navigationButtonActiveText',
  '--color-components-nav-button-bg': 'navigationButtonBackground',
  '--color-components-nav-button-bg-active': 'navigationButtonActiveBackground',
  '--color-components-nav-button-bg-hover': 'navigationButtonHoverBackground',
  '--color-components-nav-border': 'navigationBorder',
  '--color-components-side-nav-text': 'sideNavigationText',
  '--color-components-side-nav-text-active': 'sideNavigationActiveText',
  '--color-components-side-nav-text-active-bg': 'sideNavigationActiveBackground',
  '--color-components-side-nav-hover-bg': 'sideNavigationHoverBackground',
  '--color-components-side-nav-bg': 'sideNavigationBackground',
  '--color-primary-bg': 'interactionPrimaryBackground',
  '--color-modal-header-color': 'modalHeaderBackground',
  '--color-bg-image-gradient-1': 'imageGradientStart',
  '--color-bg-image-gradient-2': 'imageGradientEnd',
  '--color-portal-card-shadow': 'portalCardShadow',
  '--color-portal-surface-soft': 'portalSurfaceSoft',
  '--color-portal-surface-soft-2': 'portalSurfaceSofter',
  '--color-portal-surface-overlay': 'portalSurfaceOverlay',
  '--color-portal-preview-border': 'portalPreviewBorder',
  '--color-portal-preview-border-strong': 'portalPreviewBorderStrong',
  '--color-portal-preview-divider': 'portalPreviewDivider',
  '--color-portal-preview-shell': 'portalPreviewShell',
  '--color-portal-preview-tab-bg': 'portalPreviewTabBackground',
  '--color-portal-preview-icon-bg': 'portalPreviewIconBackground',
};

const declarationsFor = (tokens: SemanticColorTokens) => {
  const canonical = Object.entries(cssVariableMap).map(
    ([token, variable]) => `${variable}:${tokens[token as keyof SemanticColorTokens]};`
  );
  const legacy = Object.entries(legacyVariableMap).map(
    ([variable, token]) => `${variable}:var(${cssVariableMap[token]});`
  );
  return [...canonical, ...legacy].join('');
};

export const createThemeCss = (theme: ResolvedTheme) => [
  `:root,html.light{${declarationsFor(theme.light)}color-scheme:light;}`,
  `html.dark{${declarationsFor(theme.dark)}color-scheme:dark;}`,
].join('');

export const applyThemeMode = (mode: ThemeMode) => {
  document.documentElement.classList.toggle('dark', mode === 'dark');
  document.documentElement.classList.toggle('light', mode === 'light');
  document.documentElement.style.colorScheme = mode;
};

export const getAppliedThemeMode = (): ThemeMode => {
  if (typeof window === 'undefined') {
    return 'light';
  }
  return window.__BK_LITE_THEME_MODE__ === 'dark' ? 'dark' : 'light';
};

export { cssVariableMap, legacyVariableMap };
