import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { DashboardWidgetLayoutItem } from '@/app/ops-analysis/types/dashBoard';
import { hasAppAccess } from '@/context/appCapabilities/access';
import {
  type DashboardScenePermissionCode,
  isDashboardWidgetUnauthorized,
} from '@/app/ops-analysis/utils/dashboardWidgetAuth';

export const buildDataSourcesLicenseSignature = (
  dataSources: DatasourceItem[],
): string =>
  dataSources
    .map((item) => `${item.id}:${item.required_app || ''}`)
    .sort()
    .join('|');

export interface DashboardViewAuthFrozenSnapshot {
  dataSources: DatasourceItem[];
  scenePermissions: Record<string, DashboardScenePermissionCode>;
  authorizedAppNames: string[];
}

export interface DashboardViewAuthFrozenStateRefs {
  frozenRef: { current: boolean };
  frozenSnapshotRef: { current: DashboardViewAuthFrozenSnapshot | null };
  setFrozen: (next: boolean) => void;
}

export const releaseDashboardViewAuthFrozenState = ({
  frozenRef,
  frozenSnapshotRef,
  setFrozen,
}: DashboardViewAuthFrozenStateRefs) => {
  frozenRef.current = false;
  frozenSnapshotRef.current = null;
  setFrozen(false);
};

export const createDashboardViewAuthFrozenSnapshot = (
  dataSources: DatasourceItem[],
  scenePermissions: Record<string, DashboardScenePermissionCode>,
  authorizedAppNames: readonly string[],
): DashboardViewAuthFrozenSnapshot => ({
  dataSources: dataSources.map((item) => ({ ...item })),
  scenePermissions: { ...scenePermissions },
  authorizedAppNames: [...authorizedAppNames],
});

/** 新场景检查周期开始时，去掉当前待检 widget 的上周期结论（无结论按可见处理）。 */
export const stripScenePermissionsForWidgetIds = (
  scenePermissions: Record<string, DashboardScenePermissionCode>,
  widgetIds: readonly string[],
): Record<string, DashboardScenePermissionCode> => {
  if (widgetIds.length === 0) {
    return scenePermissions;
  }
  const next = { ...scenePermissions };
  widgetIds.forEach((widgetId) => {
    delete next[widgetId];
  });
  return next;
};

export const mergeScenePermissionResults = (
  results: Array<{ widget_id: string; code: DashboardScenePermissionCode }>,
): Record<string, DashboardScenePermissionCode> => {
  const next: Record<string, DashboardScenePermissionCode> = {};
  results.forEach((item) => {
    next[item.widget_id] = item.code;
  });
  return next;
};

export const createScenePermissionResultGate = () => {
  let open = true;
  return {
    close: () => {
      open = false;
    },
    isOpen: () => open,
    apply: (
      results: Array<{ widget_id: string; code: DashboardScenePermissionCode }>,
    ) => (open ? mergeScenePermissionResults(results) : null),
  };
};

export const isWidgetUnauthorizedFromFrozenSnapshot = (
  widget: DashboardWidgetLayoutItem,
  snapshot: DashboardViewAuthFrozenSnapshot | null,
): boolean => {
  if (!snapshot) {
    return false;
  }
  const apps = snapshot.authorizedAppNames.map((name) => ({ name }));
  return isDashboardWidgetUnauthorized(widget, {
    dataSources: snapshot.dataSources,
    hasAppAccess: (appName) => hasAppAccess(apps, appName),
  });
};
