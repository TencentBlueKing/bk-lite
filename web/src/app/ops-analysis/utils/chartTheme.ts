export type OpsChartThemeName = 'light' | 'dark';
export type OpsChartThemeMode = 'default' | 'screen-dark' | 'screen-light';

export const resolveOpsChartThemeName = (): OpsChartThemeName => {
  if (typeof document !== 'undefined' && document.documentElement.classList.contains('dark')) {
    return 'dark';
  }
  return 'light';
};

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
    'radial-gradient(circle at 50% 44%, rgba(42, 210, 255, 0.16), transparent 34%)',
    'radial-gradient(circle at 16% 12%, rgba(68, 150, 255, 0.12), transparent 24%)',
    'linear-gradient(135deg, #051020 0%, #08243a 48%, #030914 100%)',
  ].join(', '),
  panelChromeBg: [
    'linear-gradient(180deg, rgba(8, 34, 56, 0.54), rgba(3, 14, 30, 0.36))',
    'rgba(4, 18, 36, 0.42)',
  ].join(', '),
  panelChromeHeaderBg: 'linear-gradient(180deg, rgba(8, 38, 62, 0.58), rgba(3, 16, 34, 0.38))',
  panelChromeBorderColor: 'rgba(109, 226, 255, 0.34)',
  panelChromeShadow: [
    '0 16px 44px rgba(0, 12, 30, 0.34)',
    'inset 0 1px 0 rgba(226, 251, 255, 0.12)',
    'inset 0 -28px 52px rgba(14, 116, 144, 0.08)',
  ].join(', '),
  panelChromeBackdropFilter: 'blur(16px) saturate(128%)',
  axisLabelColor: 'rgba(221, 251, 255, 0.76)',
  axisLineColor: 'rgba(120, 223, 255, 0.22)',
  splitLineColor: 'rgba(120, 223, 255, 0.14)',
  tooltipBackgroundColor: 'rgba(5, 22, 42, 0.92)',
  tooltipBorderColor: 'rgba(109, 226, 255, 0.36)',
  tooltipTextColor: 'rgba(235, 252, 255, 0.94)',
  tooltipShadow: '0 14px 34px rgba(0, 0, 0, 0.34), 0 0 16px rgba(34, 211, 238, 0.12)',
  pieTitleColor: 'rgba(142, 235, 255, 0.72)',
  pieValueColor: '#EAFBFF',
  pieBorderColor: 'rgba(5, 18, 40, 0.94)',
  zoomBrushColor: 'rgba(54, 231, 255, 0.14)',
  zoomBrushBorderColor: 'rgba(109, 226, 255, 0.52)',
  axisPointerColor: 'rgba(125, 235, 255, 0.68)',
  legendHeaderBg: 'rgba(54, 231, 255, 0.08)',
  legendRowBg: 'rgba(8, 34, 56, 0.36)',
  legendHoverBg: 'rgba(54, 231, 255, 0.12)',
  panelBg: 'rgba(6, 24, 42, 0.48)',
  panelSubtleBg: 'rgba(68, 150, 255, 0.12)',
  panelBorderColor: 'rgba(109, 226, 255, 0.34)',
  panelTitleColor: '#EAFBFF',
  panelDescriptionColor: 'rgba(142, 235, 255, 0.68)',
  panelShadow: 'inset 0 1px 0 rgba(226, 251, 255, 0.12), 0 16px 44px rgba(0, 12, 30, 0.34)',
  singleValueColor: '#6EF4FF',
  singleValueGlow: '0 0 16px rgba(54, 231, 255, 0.28)',
  singleValueMetaColor: 'rgba(142, 235, 255, 0.68)',
  singleValueSurface: 'rgba(8, 34, 56, 0.42)',
  lineAreaOpacity: 0.18,
  lineOpacity: 0.94,
  lineShadowBlur: 6,
  lineShadowColor: 'rgba(54, 231, 255, 0.28)',
  barShadowBlur: 6,
  barShadowColor: 'rgba(54, 231, 255, 0.24)',
  topNBarShadowBlur: 6,
  topNBarShadowColor: 'rgba(54, 231, 255, 0.24)',
  pieShadowBlur: 8,
  pieShadowColor: 'rgba(54, 231, 255, 0.18)',
  panelCornerAccentColor: 'rgba(125, 235, 255, 0.58)',
};

const screenLightTheme: OpsChartTheme = {
  ...getOpsChartTheme('light'),
  axisLabelColor: '#31516f',
  axisLineColor: 'rgba(49, 81, 111, 0.22)',
  splitLineColor: 'rgba(49, 81, 111, 0.14)',
  panelBg: 'rgba(246, 252, 255, 0.82)',
  panelSubtleBg: 'rgba(14, 116, 144, 0.08)',
  panelBorderColor: 'rgba(14, 116, 144, 0.22)',
  panelTitleColor: '#083344',
  panelDescriptionColor: '#54708c',
  singleValueColor: '#0369a1',
  singleValueMetaColor: '#54708c',
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
      '#42E8F4',
      '#6EA8FF',
      '#9FE870',
      '#F9C74F',
      '#FF5D73',
      '#38BDF8',
      '#C084FC',
      '#34D399',
      '#F59E0B',
      '#F472B6',
    ];
  }

  if (mode === 'screen-light') {
    return [
      '#0891B2',
      '#2563EB',
      '#65A30D',
      '#D97706',
      '#E11D48',
      '#0284C7',
      '#7C3AED',
      '#059669',
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
