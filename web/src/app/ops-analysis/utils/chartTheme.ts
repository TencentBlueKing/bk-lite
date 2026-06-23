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

export type OpsChartTheme = ReturnType<typeof getOpsChartTheme>;

const screenDarkTheme: OpsChartTheme = {
  ...getOpsChartTheme('dark'),
  axisLabelColor: 'rgba(207, 244, 255, 0.76)',
  axisLineColor: 'rgba(76, 211, 255, 0.22)',
  splitLineColor: 'rgba(76, 211, 255, 0.16)',
  tooltipBackgroundColor: 'rgba(5, 18, 40, 0.96)',
  tooltipBorderColor: 'rgba(45, 212, 255, 0.42)',
  tooltipTextColor: 'rgba(235, 252, 255, 0.94)',
  tooltipShadow: '0 0 18px rgba(34, 211, 238, 0.22), 0 14px 34px rgba(0, 0, 0, 0.38)',
  pieTitleColor: 'rgba(142, 219, 255, 0.72)',
  pieValueColor: '#EAFBFF',
  pieBorderColor: 'rgba(5, 18, 40, 0.96)',
  zoomBrushColor: 'rgba(34, 211, 238, 0.18)',
  zoomBrushBorderColor: 'rgba(45, 212, 255, 0.62)',
  axisPointerColor: 'rgba(45, 212, 255, 0.82)',
  legendHeaderBg: 'rgba(45, 212, 255, 0.08)',
  legendRowBg: 'rgba(8, 22, 45, 0.42)',
  legendHoverBg: 'rgba(45, 212, 255, 0.12)',
  panelBg: 'rgba(7, 18, 38, 0.74)',
  panelSubtleBg: 'rgba(96, 165, 250, 0.14)',
  panelBorderColor: 'rgba(45, 212, 255, 0.34)',
  panelTitleColor: '#EAFBFF',
  panelDescriptionColor: 'rgba(142, 219, 255, 0.72)',
  panelShadow: 'inset 0 1px 0 rgba(148, 230, 255, 0.18), 0 0 22px rgba(14, 165, 233, 0.16)',
  singleValueColor: '#22D3EE',
  singleValueGlow: '0 0 16px rgba(34, 211, 238, 0.42)',
  singleValueMetaColor: 'rgba(142, 219, 255, 0.72)',
  singleValueSurface: 'rgba(8, 22, 45, 0.58)',
  lineAreaOpacity: 0.22,
  lineOpacity: 0.98,
  lineShadowBlur: 10,
  lineShadowColor: 'rgba(34, 211, 238, 0.46)',
  barShadowBlur: 12,
  barShadowColor: 'rgba(34, 211, 238, 0.38)',
  topNBarShadowBlur: 10,
  topNBarShadowColor: 'rgba(34, 211, 238, 0.42)',
  pieShadowBlur: 14,
  pieShadowColor: 'rgba(34, 211, 238, 0.24)',
  panelCornerAccentColor: 'rgba(45, 212, 255, 0.72)',
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
      '#22D3EE',
      '#60A5FA',
      '#A3E635',
      '#FACC15',
      '#FB7185',
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
