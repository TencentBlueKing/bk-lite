import { setDashboardDisplayModeInParams } from '../../shared/utils/display-mode-route';
import { hasProDashboard, resolveObjectDashboardMode } from '../../shared/utils/pro-dashboard';
import type { DashboardStyles } from '../common/dashboard-components';
import type { useSimpleDashboardData } from '../common/simple-dashboard-core';
import type { EntityLoadState } from './use-entity-metrics';

/** 主机详情第三视图。与 view=metrics 分开，避免其它对象把未知 view 当成全量指标。 */
export const HOST_DETAIL_LAYOUT_PARAM = 'host_layout';

export type HostDetailLayout = 'dashboard' | 'metrics' | 'category';

export interface HostDetailLayoutOption {
  labelKey: string;
  fallback: string;
  value: HostDetailLayout;
}

export const HOST_DETAIL_LAYOUT_OPTIONS: readonly HostDetailLayoutOption[] = [
  { labelKey: 'dashboardMode', fallback: '传统仪表盘', value: 'dashboard' },
  { labelKey: 'categoryTabMode', fallback: '专业仪表盘', value: 'category' },
  { labelKey: 'metricsMode', fallback: '全量指标', value: 'metrics' }
];

export const isHostDetailLayout = (value: string): value is HostDetailLayout => (
  value === 'dashboard' || value === 'metrics' || value === 'category'
);

/** 未指定布局时按能力表默认专业。显式 host_layout=dashboard 才回传统。 */
export const readHostDetailLayout = (
  params: URLSearchParams,
  professionalCapable = hasProDashboard('host')
): HostDetailLayout => {
  const mode = resolveObjectDashboardMode('host', params, HOST_DETAIL_LAYOUT_PARAM);
  if (mode === 'metrics') return 'metrics';
  if (!professionalCapable) return 'dashboard';
  return mode;
};

export const writeHostDetailLayout = (
  params: URLSearchParams,
  layout: HostDetailLayout
) => {
  const next = setDashboardDisplayModeInParams(params, layout === 'metrics' ? 'metrics' : 'dashboard');
  if (layout === 'category') next.set(HOST_DETAIL_LAYOUT_PARAM, 'category');
  else if (layout === 'dashboard') next.set(HOST_DETAIL_LAYOUT_PARAM, 'dashboard');
  else next.delete(HOST_DETAIL_LAYOUT_PARAM);
  return next;
};

export interface HostDetailLayoutProps {
  styles: DashboardStyles;
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  instanceIdKeys: string[];
  diskState: EntityLoadState;
  netState: EntityLoadState;
  processReady: boolean;
  processState?: EntityLoadState;
  gpuState?: EntityLoadState;
  layout?: HostDetailLayout;
  onLayoutChange?: (mode: string) => void;
  categoryTab?: string;
  onCategoryTabChange?: (tab: string) => void;
}
