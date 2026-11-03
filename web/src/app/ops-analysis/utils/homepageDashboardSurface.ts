export interface DashboardChromeSurface {
  canvasBackground: string;
  groupBackground: string;
  groupHeaderBackground: string;
  groupBorderColor: string;
  groupHeaderBorder: string;
  groupBackdrop: string;
}

const OPS_ANALYSIS_LIGHT: DashboardChromeSurface = {
  canvasBackground: '#f7f8fa',
  groupBackground: '#f7f8fa',
  groupHeaderBackground: '#f1f3f8',
  groupBorderColor: 'rgba(61,79,104,0.14)',
  groupHeaderBorder: '1px solid rgba(61,79,104,0.08)',
  groupBackdrop: '',
};

const OPS_ANALYSIS_DARK: DashboardChromeSurface = {
  canvasBackground: 'var(--color-bg-2)',
  groupBackground: 'rgba(255,255,255,0.02)',
  groupHeaderBackground: 'rgba(255,255,255,0.03)',
  groupBorderColor: 'rgba(255,255,255,0.12)',
  groupHeaderBorder: '1px solid rgba(255,255,255,0.08)',
  groupBackdrop: '',
};

/**
 * 浅色首页透出 system-bg，分组只铺一层薄白。
 * 深色首页没有这张底图，继续用运营分析的深色底。
 */
const HOMEPAGE_LIGHT: DashboardChromeSurface = {
  canvasBackground: 'transparent',
  groupBackground: 'rgba(255,255,255,0.46)',
  groupHeaderBackground: 'rgba(255,255,255,0.28)',
  groupBorderColor: 'rgba(120,156,190,0.2)',
  groupHeaderBorder: '1px solid rgba(120,156,190,0.12)',
  groupBackdrop: 'blur(12px)',
};

export const resolveDashboardChrome = (
  homepage: boolean,
  dark: boolean,
): DashboardChromeSurface => {
  if (homepage && !dark) {
    return HOMEPAGE_LIGHT;
  }
  return dark ? OPS_ANALYSIS_DARK : OPS_ANALYSIS_LIGHT;
};
