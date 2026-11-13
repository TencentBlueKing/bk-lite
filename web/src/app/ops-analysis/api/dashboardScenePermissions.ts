import { useCallback } from 'react';
import { usePathname } from 'next/navigation';
import useApiClient from '@/utils/request';
import type { DashboardScenePermissionCode } from '@/app/ops-analysis/utils/dashboardWidgetAuth';
import { delegatedSceneBase } from './displayDelegate';

export interface DashboardScenePermissionCheck {
  widget_id: string;
  scene_type: 'relatedTopology' | 'applicationTopology';
  inst_uuid?: string;
}

export interface DashboardScenePermissionResult {
  widget_id: string;
  code: DashboardScenePermissionCode;
}

const DASHBOARD_SCENE_PERMISSIONS_PATH =
  '/operation_analysis/api/scene_widgets/dashboard_scene_permissions/';

export const dashboardScenePermissionsApiPath = (
  shareSessionId?: string,
  pathname?: string | null,
) => delegatedSceneBase(
  pathname,
  shareSessionId,
  'dashboard_scene_permissions/',
  DASHBOARD_SCENE_PERMISSIONS_PATH,
);

export const useDashboardScenePermissionsApi = (shareSessionId?: string) => {
  const { post } = useApiClient();
  const path = dashboardScenePermissionsApiPath(shareSessionId, usePathname());

  const checkDashboardScenePermissions = useCallback(
    async (checks: DashboardScenePermissionCheck[]) => {
      if (checks.length === 0) {
        return [] as DashboardScenePermissionResult[];
      }
      const response = await post<{ results: DashboardScenePermissionResult[] }>(
        path,
        { checks },
        { suppressErrorNotification: true },
      );
      return Array.isArray(response?.results) ? response.results : [];
    },
    [path, post],
  );

  return { checkDashboardScenePermissions };
};
