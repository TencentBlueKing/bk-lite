import type { AppWidgetKey } from '@/context/appCapabilities/widgets';
import { canShowCrossModulePublicWidget } from '@/context/appCapabilities/crossModuleEmbed';

export interface CmdbPublicMenuItem {
  key:
    | 'monitorView'
    | 'alertList'
    | 'networkStatusTopology'
    | 'application3D';
  widgetKey: AppWidgetKey;
  titleKey: string;
  url: string;
}

const DETAIL_BASE = '/cmdb/assetData/detail';

export function resolveCmdbPublicMenuItems(input: {
  instUuid: string;
  modelId: string;
  monitorId: string;
  isNetworkDevice: boolean;
  hasOpsAnalysis: boolean;
  widgets: Partial<Record<AppWidgetKey, boolean>>;
}): CmdbPublicMenuItem[] {
  const instUuid = input.instUuid.trim();
  const monitorId = input.monitorId.trim();
  const items: CmdbPublicMenuItem[] = [];
  const canShow = (widgetKey: AppWidgetKey) =>
    canShowCrossModulePublicWidget({
      hostApp: 'cmdb',
      widgetKey,
      hasOpsAnalysis: input.hasOpsAnalysis,
      providerDeclared: Boolean(input.widgets[widgetKey]),
    });

  if (monitorId && canShow('monitor.monitorView')) {
    items.push({
      key: 'monitorView',
      widgetKey: 'monitor.monitorView',
      titleKey: 'Model.publicMonitorView',
      url: `${DETAIL_BASE}/monitorView`,
    });
  }
  if (monitorId && canShow('monitor.alertList')) {
    items.push({
      key: 'alertList',
      widgetKey: 'monitor.alertList',
      titleKey: 'Model.publicAlertList',
      url: `${DETAIL_BASE}/alertList`,
    });
  }
  if (!instUuid) {
    return items;
  }
  if (input.isNetworkDevice && canShow('ops-analysis.networkStatusTopology')) {
    items.push({
      key: 'networkStatusTopology',
      widgetKey: 'ops-analysis.networkStatusTopology',
      titleKey: 'Model.publicNetworkStatusTopology',
      url: `${DETAIL_BASE}/networkStatusTopology`,
    });
  }
  if (input.modelId === 'system' && canShow('ops-analysis.application3D')) {
    items.push({
      key: 'application3D',
      widgetKey: 'ops-analysis.application3D',
      titleKey: 'Model.publicApplication3D',
      url: `${DETAIL_BASE}/application3D`,
    });
  }
  return items;
}
