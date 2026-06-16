export type OpsChartThemeName = 'light' | 'dark';

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
  };
};
