import {
  effectiveHomepageHref,
  isDashboardHomepagePath,
} from '@/app/ops-analysis/utils/homepageLanding';
import type { HomepagePreferenceState } from '@/app/ops-analysis/utils/homepageDirectoryActions';

export type HomepagePersonalMode = HomepagePreferenceState['personal_mode'];

export const OPS_ANALYSIS_APP = 'ops-analysis';
export const OPS_ANALYSIS_VIEW_PATH = '/ops-analysis/view';

export interface MenuPermissionNode {
  name?: string | null;
  operation?: readonly string[] | null;
  children?: readonly MenuPermissionNode[] | null;
}

/**
 * 父行右侧 i18n：跟随→默认首页，控制台→控制台。
 * 个人盘由调用方直接显示盘名；未知/加载中返回 null，避免左右都写「首页」。
 */
export const homepageParentLabelKey = (
  mode: HomepagePersonalMode | null | undefined,
): string | null => {
  if (mode === 'follow') {
    return 'common.homepageFollowGlobal';
  }
  if (mode === 'workbench') {
    return 'common.homepagePinWorkbench';
  }
  return null;
};

/** 父行右侧展示文案：有个人盘名用盘名，否则走 i18n 短状态。 */
export const homepageParentRightLabel = (
  mode: HomepagePersonalMode | null | undefined,
  dashboardName: string | null | undefined,
): { kind: 'text'; value: string } | { kind: 'i18n'; key: string } | null => {
  if (mode === 'dashboard') {
    const name = dashboardName?.trim();
    return name ? { kind: 'text', value: name } : null;
  }
  const key = homepageParentLabelKey(mode);
  return key ? { kind: 'i18n', key } : null;
};

/** 单选只认 personal_mode。dashboard 与未知状态两项都不勾。 */
export const homepageRadioChecked = (
  mode: HomepagePersonalMode | null | undefined,
  option: 'follow' | 'workbench',
): boolean => mode === option;

export const followGlobalDescription = (
  base: string,
  currentLabel: (name: string) => string,
  adminName: string | null | undefined,
): string => {
  const name = adminName?.trim();
  if (!name) {
    return base;
  }
  return `${base}${currentLabel(name)}`;
};

/**
 * 个人盘说明。名称还在取时返回 null，避免先画出兜底文案。
 * 取完没有名称时用 fallback。
 */
export const personalDashboardCaption = (
  mode: HomepagePersonalMode | null | undefined,
  name: string | null | undefined,
  resolved: boolean,
  fallback: string,
): string | null => {
  if (mode !== 'dashboard') {
    return null;
  }
  if (!resolved) {
    return null;
  }
  const trimmed = name?.trim();
  return trimmed || fallback;
};

/** clear 之后按全局绑定跳：管理员绑了盘进盘，否则工作台。 */
export const hrefAfterFollowGlobal = (
  state: Pick<HomepagePreferenceState, 'global_mode' | 'global_dashboard_id'> | null | undefined,
): string => {
  const dashboardId = state?.global_dashboard_id;
  if (state?.global_mode === 'dashboard' && dashboardId) {
    return effectiveHomepageHref({ dashboardId });
  }
  return effectiveHomepageHref(null);
};

export const hrefAfterPinWorkbench = (): string => effectiveHomepageHref(null);

const positiveDashboardId = (value: string | number | null | undefined): number | null => {
  if (value == null) {
    return null;
  }
  const raw = String(value).trim();
  if (!/^[1-9]\d*$/.test(raw)) {
    return null;
  }
  return Number(raw);
};

/** 当前首页对应的仪表盘。控制台偏好没有可打开的盘。 */
export const effectiveHomepageDashboardId = (
  state: Pick<
    HomepagePreferenceState,
    'personal_mode' | 'personal_dashboard_id' | 'global_mode' | 'global_dashboard_id'
  > | null | undefined,
): number | null => {
  if (!state || state.personal_mode === 'workbench') {
    return null;
  }
  if (state.personal_mode === 'dashboard') {
    return positiveDashboardId(state.personal_dashboard_id);
  }
  if (state.global_mode === 'dashboard') {
    return positiveDashboardId(state.global_dashboard_id);
  }
  return null;
};

/**
 * 「选择仪表盘作为首页」要打开的盘。
 * 正在看首页嵌入时用地址栏上的盘，否则用已保存的首页盘。
 */
export const settingsDashboardId = (
  state: Parameters<typeof effectiveHomepageDashboardId>[0],
  pathname: string | null | undefined,
  search: string | { get: (name: string) => string | null } | null | undefined,
): number | null => {
  if (isDashboardHomepagePath(pathname, search)) {
    const raw = typeof search === 'string'
      ? new URLSearchParams(search.replace(/^\?/, '')).get('dashboard_id')
      : search?.get('dashboard_id');
    const viewingId = positiveDashboardId(raw);
    if (viewingId) {
      return viewingId;
    }
  }
  return effectiveHomepageDashboardId(state);
};

/**
 * 无运营分析模块、无 view-View，或 client / 菜单还在加载时，不画「前往仪表盘设置」。
 */
export const canShowDashboardSettingsLink = (input: {
  clientLoading: boolean;
  hasModule: boolean;
  viewAllowed: boolean | null;
}): boolean => {
  if (input.clientLoading || !input.hasModule) {
    return false;
  }
  return input.viewAllowed === true;
};

export const menuGrantsOpsAnalysisView = (menus: unknown): boolean => {
  const visit = (items: unknown): boolean => {
    if (!Array.isArray(items) || items.length === 0) {
      return false;
    }
    return items.some((item) => {
      if (!item || typeof item !== 'object') {
        return false;
      }
      const node = item as MenuPermissionNode;
      const operations = Array.isArray(node.operation) ? node.operation : [];
      if (node.name === 'view' && operations.includes('View')) {
        return true;
      }
      return visit(node.children);
    });
  };
  return visit(menus);
};
