import type { DatasourceItem } from '../types/dataSource';
import type { DashboardWidgetLayoutItem } from '../types/dashBoard';
import { normalizeDatasourceRecordId } from './datasourceRecordId';

export type DashboardScenePermissionCode = 'permission_denied' | 'visible';

/** 场景组件不读数据源字段；窄白名单对应模块许可。 */
export const DASHBOARD_SCENE_REQUIRED_APP: Record<string, string> = {
  relatedTopology: 'cmdb',
  applicationTopology: 'cmdb',
  networkStatusTopology: 'cmdb',
};

export const resolveDashboardWidgetDataSourceId = (
  widget: DashboardWidgetLayoutItem,
): number | undefined => {
  const rawId = widget.valueConfig?.dataSource;
  const normalizedId = typeof rawId === 'string' ? parseInt(rawId, 10) : rawId;
  return Number.isFinite(normalizedId) ? (normalizedId as number) : undefined;
};

export const resolveDashboardWidgetSceneType = (
  widget: DashboardWidgetLayoutItem,
): string | undefined => {
  const legacyChartType = (widget as { chartType?: string }).chartType;
  return widget.valueConfig?.sceneWidgetType || widget.valueConfig?.chartType || legacyChartType;
};

export const resolveDashboardSceneInstUuid = (
  widget: DashboardWidgetLayoutItem,
): string => {
  const sceneType = resolveDashboardWidgetSceneType(widget);
  if (sceneType === 'relatedTopology') {
    return widget.valueConfig?.relatedTopology?.instUuid?.trim() || '';
  }
  if (sceneType === 'applicationTopology') {
    return widget.valueConfig?.applicationTopology?.instUuid?.trim() || '';
  }
  return '';
};

export const isDashboardWidgetUnauthorized = (
  widget: DashboardWidgetLayoutItem,
  options: {
    dataSources: DatasourceItem[];
    hasAppAccess: (appName: string) => boolean;
  },
): boolean => {
  const sceneType = resolveDashboardWidgetSceneType(widget);
  const sceneApp = sceneType ? DASHBOARD_SCENE_REQUIRED_APP[sceneType] : undefined;
  if (sceneApp) {
    return !options.hasAppAccess(sceneApp);
  }

  const dataSourceId = resolveDashboardWidgetDataSourceId(widget);
  if (!dataSourceId) {
    return false;
  }

  const dataSource = options.dataSources.find(
    (item) => normalizeDatasourceRecordId(item.id) === dataSourceId,
  );
  if (!dataSource) {
    return false;
  }

  const requiredApp = dataSource.required_app?.trim();
  if (!requiredApp) {
    return false;
  }
  return !options.hasAppAccess(requiredApp);
};
