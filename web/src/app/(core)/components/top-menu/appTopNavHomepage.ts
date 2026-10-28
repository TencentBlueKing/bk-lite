import {
  findActiveApp,
  isAppNavActive,
  shouldStayOnCurrentAppPage,
} from '@/console-layout';
import { isDashboardHomepagePath } from '@/app/ops-analysis/utils/homepageLanding';

type SearchLike = string | { get: (name: string) => string | null } | null | undefined;

type AppNavTarget =
  | { mode: 'same-tab'; href: string }
  | { mode: 'new-tab'; href: string };

/**
 * 顶栏高亮仍按路由归属。
 * 唯一例外：/ops-console/home?dashboard_id=… 是「挂在控制台路径上的仪表盘壳」，
 * 不算控制台工作台，也不伪装成运营分析 —— 两边都不高亮。
 */
export const isAppTopNavActive = (
  app: { url: string; name?: string },
  pathname: string | null,
  origin: string,
  search: SearchLike,
): boolean => {
  if (!pathname) {
    return false;
  }
  if (isDashboardHomepagePath(pathname, search)) {
    return false;
  }
  return isAppNavActive(app, pathname, origin);
};

/** 仪表盘壳上控制台不高亮，点击不会被 stay 吃掉，自然落到裸 /ops-console/home。 */
export const shouldStayOnAppTopNavClick = (
  active: boolean,
  target: AppNavTarget,
): boolean => shouldStayOnCurrentAppPage(active, target);

export const findAppTopNavActiveApp = <T extends { url: string; name?: string }>(
  apps: T[],
  pathname: string | null,
  origin: string,
  search: SearchLike,
): T | undefined => {
  if (!pathname || isDashboardHomepagePath(pathname, search)) {
    return undefined;
  }
  return findActiveApp(apps, pathname, origin);
};
