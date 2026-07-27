export type ThemeMode = 'light' | 'dark';

export interface SemanticColorTokens {
  interactionPrimary: string;
  interactionPrimarySoft: string;
  interactionPrimaryActiveBackground: string;
  interactionPrimaryBackground: string;
  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  textDisabled: string;
  textActive: string;
  textHoverBackground: string;
  surfacePage: string;
  surfaceContainer: string;
  surfaceHover: string;
  surfaceMuted: string;
  surfaceLevel1: string;
  surfaceLevel2: string;
  surfaceLevel3: string;
  surfaceLevel4: string;
  surfaceLevel5: string;
  surfaceTranslucent: string;
  surfaceTranslucentSubtle: string;
  borderDefault: string;
  borderSubtle: string;
  borderMuted: string;
  borderStrong: string;
  borderEmphasis: string;
  fillSubtle: string;
  fillMuted: string;
  fillDefault: string;
  fillStrong: string;
  fillEmphasis: string;
  statusSuccess: string;
  statusWarning: string;
  statusInfo: string;
  statusError: string;
  navigationButtonText: string;
  navigationButtonActiveText: string;
  navigationButtonBackground: string;
  navigationButtonActiveBackground: string;
  navigationButtonHoverBackground: string;
  navigationBorder: string;
  sideNavigationText: string;
  sideNavigationActiveText: string;
  sideNavigationActiveBackground: string;
  sideNavigationHoverBackground: string;
  sideNavigationBackground: string;
  modalHeaderBackground: string;
  imageGradientStart: string;
  imageGradientEnd: string;
  portalCardShadow: string;
  portalSurfaceSoft: string;
  portalSurfaceSofter: string;
  portalSurfaceOverlay: string;
  portalPreviewBorder: string;
  portalPreviewBorderStrong: string;
  portalPreviewDivider: string;
  portalPreviewShell: string;
  portalPreviewTabBackground: string;
  portalPreviewIconBackground: string;
  chartAxisLine: string;
  chartSplitLine: string;
  chartAxisLabel: string;
  chartBackground: string;
  chartTooltipBackground: string;
  chartTooltipBorder: string;
  chartTextPrimary: string;
  chartTextSecondary: string;
  chartTextTertiary: string;
  chartPrimary: string;
  chartSuccess: string;
  chartWarning: string;
  chartError: string;
}

export interface ThemeMetadata {
  themeId: string;
  themeVersion: string;
  schemaVersion: number;
}

export interface ThemeDefinition extends ThemeMetadata {
  light: Partial<SemanticColorTokens>;
  dark: Partial<SemanticColorTokens>;
}

export interface ResolvedTheme extends ThemeMetadata {
  light: SemanticColorTokens;
  dark: SemanticColorTokens;
}
