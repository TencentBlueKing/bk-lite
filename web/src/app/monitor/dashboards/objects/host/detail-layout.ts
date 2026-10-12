import { setDashboardDisplayModeInParams } from '../../shared/utils/display-mode-route';
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
  { labelKey: 'dashboardMode', fallback: '监控仪表盘', value: 'dashboard' },
  { labelKey: 'metricsMode', fallback: '全量指标', value: 'metrics' },
  { labelKey: 'categoryTabMode', fallback: '概览→分类 Tab→再下钻', value: 'category' }
];

export const isHostDetailLayout = (value: string): value is HostDetailLayout => (
  value === 'dashboard' || value === 'metrics' || value === 'category'
);

export const readHostDetailLayout = (params: URLSearchParams): HostDetailLayout => {
  if (params.get('view') === 'metrics') return 'metrics';
  return params.get(HOST_DETAIL_LAYOUT_PARAM) === 'category' ? 'category' : 'dashboard';
};

export const writeHostDetailLayout = (
  params: URLSearchParams,
  layout: HostDetailLayout
) => {
  const next = setDashboardDisplayModeInParams(params, layout === 'metrics' ? 'metrics' : 'dashboard');
  if (layout === 'category') next.set(HOST_DETAIL_LAYOUT_PARAM, 'category');
  else next.delete(HOST_DETAIL_LAYOUT_PARAM);
  return next;
};

export interface HostDetailLayoutProps {
  styles: DashboardStyles;
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  instanceIdKeys: string[];
  diskState: EntityLoadState;
  netState: EntityLoadState;
  gpuState: EntityLoadState;
  processReady: boolean;
}
