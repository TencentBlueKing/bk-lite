export type ObjectDashboardMode = 'dashboard' | 'category' | 'metrics';

/**
 * 代码里真正挂了专业盘的对象。只收录已有专业布局的路由，
 * 不按名字猜测。目前是主机分类盘和 MySQL 专业盘。
 */
const PRO_DASHBOARD_OBJECT_KEYS = ['host', 'mysql'] as const;

export interface DashboardModeOptionShape {
  labelKey: string;
  fallback: string;
  value: ObjectDashboardMode;
  disabled?: boolean;
}

export const hasProDashboard = (objectKey: string) => (
  (PRO_DASHBOARD_OBJECT_KEYS as readonly string[]).includes(objectKey.trim().toLowerCase())
);

/** URL 已钉死的模式。没有记录时返回 null，交给默认规则。 */
export const readPinnedDashboardMode = (
  params: URLSearchParams,
  layoutParam = 'dash_layout'
): ObjectDashboardMode | null => {
  if (params.get('view') === 'metrics') return 'metrics';
  const layout = params.get(layoutParam);
  if (layout === 'dashboard' || layout === 'category') return layout;
  return null;
};

/**
 * 有记录就用记录。没记录时：有专业盘默认专业，没有则默认传统。
 * 无专业盘即使 URL 写了 category，也落回传统，避免进空壳。
 */
export const resolveObjectDashboardMode = (
  objectKey: string,
  params: URLSearchParams,
  layoutParam = 'dash_layout'
): ObjectDashboardMode => {
  const pinned = readPinnedDashboardMode(params, layoutParam);
  if (pinned === 'metrics' || pinned === 'dashboard') return pinned;
  if (pinned === 'category') return hasProDashboard(objectKey) ? 'category' : 'dashboard';
  return hasProDashboard(objectKey) ? 'category' : 'dashboard';
};

export const dashboardModeOptions = (objectKey: string): readonly DashboardModeOptionShape[] => {
  const pro = hasProDashboard(objectKey);
  return [
    { labelKey: 'dashboardMode', fallback: '传统仪表盘', value: 'dashboard', disabled: false },
    { labelKey: 'categoryTabMode', fallback: '专业仪表盘', value: 'category', disabled: !pro },
    { labelKey: 'metricsMode', fallback: '全量指标', value: 'metrics', disabled: false }
  ];
};

export const writeObjectDashboardMode = (
  params: URLSearchParams,
  mode: ObjectDashboardMode,
  layoutParam = 'dash_layout'
) => {
  const next = new URLSearchParams(params.toString());
  if (mode === 'metrics') {
    next.set('view', 'metrics');
    next.delete(layoutParam);
  } else {
    next.delete('view');
    next.set(layoutParam, mode);
  }
  return next;
};
