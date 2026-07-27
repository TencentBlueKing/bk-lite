import { getAppliedThemeMode } from '@/theme';

export type OpsChartThemeName = 'light' | 'dark';
export type OpsChartThemeMode = 'default' | 'screen-dark' | 'screen-light';

export const isScreenChartThemeMode = (
  mode?: OpsChartThemeMode,
) => mode === 'screen-dark' || mode === 'screen-light';

export const resolveOpsChartThemeName = (): OpsChartThemeName => getAppliedThemeMode();

export const getOpsChartTheme = (themeName: OpsChartThemeName) => {
  const isDarkTheme = themeName === 'dark';

  return {
    axisLabelColor: isDarkTheme ? 'rgba(255,255,255,0.64)' : '#7f92a7',
    axisLineColor: isDarkTheme ? 'rgba(255,255,255,0.14)' : '#e5ebf4',
    splitLineColor: isDarkTheme ? 'rgba(255,255,255,0.12)' : '#e8eef7',
    tooltipBackgroundColor: isDarkTheme ? 'rgba(7, 29, 44, 0.96)' : '#ffffff',
    tooltipBorderColor: isDarkTheme ? 'rgba(255,255,255,0.12)' : '#e6e9ee',
    tooltipTextColor: isDarkTheme ? 'rgba(255,255,255,0.88)' : '#1e252e',
    tooltipShadow: isDarkTheme ? '0 12px 32px rgba(0,0,0,0.36)' : '0 8px 24px rgba(15,23,42,0.12)',
    pieTitleColor: isDarkTheme ? 'rgba(255,255,255,0.58)' : '#7a8699',
    pieValueColor: isDarkTheme ? 'rgba(255,255,255,0.92)' : '#2a3547',
    pieBorderColor: isDarkTheme ? 'rgba(7, 29, 44, 0.96)' : '#fff',
    zoomBrushColor: isDarkTheme ? 'rgba(46, 132, 255, 0.14)' : 'rgba(24, 144, 255, 0.12)',
    zoomBrushBorderColor: isDarkTheme ? 'rgba(96, 165, 250, 0.52)' : 'rgba(24, 144, 255, 0.42)',
    axisPointerColor: isDarkTheme ? 'rgba(96, 165, 250, 0.72)' : 'rgba(60, 102, 240, 0.55)',
    legendHeaderBg: isDarkTheme ? 'rgba(255,255,255,0.06)' : '#f7f9fc',
    legendRowBg: isDarkTheme ? 'rgba(255,255,255,0.03)' : '#fbfcfe',
    legendHoverBg: isDarkTheme ? 'rgba(255,255,255,0.08)' : '#eef4ff',
    panelBg: isDarkTheme ? 'var(--color-bg-1)' : '#ffffff',
    panelSubtleBg: isDarkTheme ? 'rgba(255,255,255,0.03)' : '#fbfdff',
    panelBorderColor: isDarkTheme ? 'var(--color-border-2)' : '#e6edf7',
    panelTitleColor: isDarkTheme ? 'rgba(255,255,255,0.88)' : 'var(--color-text-1)',
    panelDescriptionColor: isDarkTheme ? 'rgba(255,255,255,0.56)' : 'var(--color-text-3)',
    panelShadow: isDarkTheme
      ? '0 10px 28px rgba(0, 0, 0, 0.24)'
      : '0 10px 30px rgba(31, 63, 104, 0.08)',
    singleValueColor: isDarkTheme ? 'rgba(255,255,255,0.94)' : '#1e40af',
    singleValueGlow: isDarkTheme ? 'none' : '0 4px 14px rgba(30, 64, 175, 0.08)',
    singleValueMetaColor: isDarkTheme ? 'rgba(255,255,255,0.52)' : '#7f92a7',
    singleValueSurface: isDarkTheme ? 'rgba(255,255,255,0.02)' : '#fcfdff',
    lineWidth: isDarkTheme ? 2 : 2,
    lineAreaOpacity: isDarkTheme ? 0.1 : 0.06,
    lineOpacity: isDarkTheme ? 0.94 : 0.92,
    lineShadowBlur: 0,
    lineShadowColor: 'transparent',
    barShadowBlur: 0,
    barShadowColor: 'transparent',
    topNBarShadowBlur: 0,
    topNBarShadowColor: 'transparent',
    pieShadowBlur: 0,
    pieShadowColor: 'transparent',
    panelCornerAccentColor: isDarkTheme
      ? 'rgba(255, 255, 255, 0.16)'
      : 'rgba(24, 144, 255, 0.22)',
  };
};

type BaseOpsChartTheme = ReturnType<typeof getOpsChartTheme>;

export type OpsChartTheme = BaseOpsChartTheme & {
  screenCanvasBg?: string;
  panelChromeBg?: string;
  panelChromeHeaderBg?: string;
  panelChromeBorderColor?: string;
  panelChromeShadow?: string;
  panelChromeBackdropFilter?: string;
};

const screenDarkTheme: OpsChartTheme = {
  ...getOpsChartTheme('dark'),
  screenCanvasBg: [
    'radial-gradient(circle at 50% 4%, rgba(89, 177, 255, 0.2), transparent 32%)',
    'radial-gradient(circle at 7% 48%, rgba(58, 139, 226, 0.12), transparent 28%)',
    'linear-gradient(145deg, #173754 0%, #102c49 50%, #0c2138 100%)',
  ].join(', '),
  panelChromeBg: 'linear-gradient(180deg, rgba(32, 68, 102, 0.74), rgba(13, 40, 68, 0.66))',
  panelChromeHeaderBg: 'linear-gradient(90deg, rgba(51, 102, 151, 0.34), rgba(18, 41, 66, 0.54) 72%)',
  panelChromeBorderColor: 'rgba(124, 193, 251, 0.34)',
  panelChromeShadow: '0 11px 27px rgba(0, 10, 24, 0.22), inset 0 1px 0 rgba(215, 238, 251, 0.09)',
  panelChromeBackdropFilter: 'blur(10px) saturate(114%)',
  axisLabelColor: 'rgba(220, 231, 244, 0.88)',
  axisLineColor: 'rgba(112, 147, 195, 0.22)',
  splitLineColor: 'rgba(112, 147, 195, 0.14)',
  tooltipBackgroundColor: 'rgba(10, 19, 32, 0.96)',
  tooltipBorderColor: 'rgba(112, 147, 195, 0.3)',
  tooltipTextColor: 'rgba(232, 238, 247, 0.94)',
  tooltipShadow: '0 10px 24px rgba(0, 0, 0, 0.32)',
  pieTitleColor: 'rgba(211, 225, 241, 0.82)',
  pieValueColor: '#eef4fc',
  pieBorderColor: '#0e192a',
  zoomBrushColor: 'rgba(91, 143, 249, 0.14)',
  zoomBrushBorderColor: 'rgba(91, 143, 249, 0.52)',
  axisPointerColor: 'rgba(115, 167, 255, 0.68)',
  legendHeaderBg: 'rgba(91, 143, 249, 0.08)',
  legendRowBg: 'rgba(20, 36, 58, 0.72)',
  legendHoverBg: 'rgba(91, 143, 249, 0.12)',
  panelBg: 'rgba(13, 40, 68, 0.66)',
  panelSubtleBg: 'rgba(91, 143, 249, 0.08)',
  panelBorderColor: 'rgba(112, 147, 195, 0.24)',
  panelTitleColor: '#e8eef7',
  panelDescriptionColor: 'rgba(211, 225, 241, 0.8)',
  panelShadow: '0 11px 27px rgba(0, 10, 24, 0.22), inset 0 1px 0 rgba(215, 238, 251, 0.09)',
  singleValueColor: '#73A7FF',
  singleValueGlow: 'none',
  singleValueMetaColor: 'rgba(211, 225, 241, 0.8)',
  singleValueSurface: 'rgba(14, 25, 42, 0.72)',
  lineAreaOpacity: 0.12,
  lineOpacity: 0.94,
  lineShadowBlur: 0,
  lineShadowColor: 'transparent',
  barShadowBlur: 0,
  barShadowColor: 'transparent',
  topNBarShadowBlur: 0,
  topNBarShadowColor: 'transparent',
  pieShadowBlur: 0,
  pieShadowColor: 'transparent',
  panelCornerAccentColor: 'rgba(115, 167, 255, 0.5)',
};

const screenLightTheme: OpsChartTheme = {
  ...getOpsChartTheme('light'),
  panelChromeBg: 'linear-gradient(145deg, rgba(255, 255, 255, 0.2), rgba(243, 247, 251, 0.07))',
  panelChromeHeaderBg: 'linear-gradient(90deg, rgba(225, 235, 246, 0.1), rgba(255, 255, 255, 0.02) 74%)',
  panelChromeBorderColor: 'rgba(101, 126, 160, 0.28)',
  panelChromeShadow: '0 10px 24px rgba(31, 47, 70, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.98), inset 1px 0 0 rgba(255, 255, 255, 0.52)',
  panelChromeBackdropFilter: 'blur(10px) saturate(120%)',
  axisLabelColor: '#53657a',
  axisLineColor: 'rgba(71, 91, 117, 0.2)',
  splitLineColor: 'rgba(71, 91, 117, 0.12)',
  legendHeaderBg: 'rgba(226, 235, 245, 0.1)',
  legendRowBg: 'rgba(255, 255, 255, 0.04)',
  legendHoverBg: 'rgba(226, 237, 251, 0.46)',
  panelBg: 'rgba(255, 255, 255, 0.06)',
  panelSubtleBg: 'rgba(241, 246, 251, 0.03)',
  panelBorderColor: 'rgba(121, 145, 176, 0.14)',
  panelTitleColor: '#17243a',
  panelDescriptionColor: '#65758b',
  singleValueColor: '#2468d8',
  singleValueGlow: 'none',
  singleValueMetaColor: '#65758b',
  singleValueSurface: 'transparent',
};

export const getOpsChartThemeByMode = (
  mode: OpsChartThemeMode | undefined,
): OpsChartTheme => {
  if (mode === 'screen-dark') return screenDarkTheme;
  if (mode === 'screen-light') return screenLightTheme;
  return getOpsChartTheme(resolveOpsChartThemeName());
};

export const getOpsChartColorsByMode = (
  mode: OpsChartThemeMode | undefined,
  themeName: OpsChartThemeName = resolveOpsChartThemeName(),
) => {
  if (mode === 'screen-dark') {
    return [
      '#5B8FF9',
      '#5AD8D8',
      '#9270CA',
      '#F6BD16',
      '#E8684A',
      '#6DC8EC',
      '#945FB9',
      '#5D7092',
      '#FF9D4D',
      '#E864B3',
    ];
  }

  if (mode === 'screen-light') {
    return [
      '#2F6BDE',
      '#168AAD',
      '#7656C8',
      '#D89216',
      '#D6535D',
      '#3A8DDE',
      '#8B5FBF',
      '#64748B',
    ];
  }

  return themeName === 'dark'
    ? [
      '#5B8CFF',
      '#36CFC9',
      '#73D13D',
      '#FFC53D',
      '#FF7875',
      '#40A9FF',
      '#B37FEB',
      '#5CDBD3',
    ]
    : [
      '#5470C6',
      '#91CC75',
      '#FAC858',
      '#EE6666',
      '#73C0DE',
      '#3BA272',
      '#FC8452',
      '#9A60B4',
    ];
};
