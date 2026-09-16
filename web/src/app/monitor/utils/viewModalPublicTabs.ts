import { canShowCrossModulePublicWidget } from '@/context/appCapabilities/crossModuleEmbed';
import type { AppWidgetKey } from '@/context/appCapabilities/widgets';

export interface ViewModalPublicTabItem {
  key: 'relatedTopology' | 'baseInfo' | 'assetChange' | 'nodeStatus';
  label: string;
  identifierProp: 'instUuid' | 'nodeId';
}

export function readViewModalStableIds(form: Record<string, unknown> | null | undefined): {
  monitorId: string;
  instUuid: string;
  nodeId: string;
} {
  const read = (value: unknown) =>
    typeof value === 'string' ? value.trim() : '';
  return {
    monitorId: read(form?.instance_id),
    instUuid: read(form?.cmdb_id),
    nodeId: read(form?.node_id),
  };
}

export function buildViewModalLocalTabs(
  t: (id: string) => string,
): Array<{ key: string; label: string }> {
  return [
    { key: 'monitorView', label: t('monitor.views.monitorView') },
    { key: 'alertList', label: t('monitor.views.alertList') },
    { key: 'monitorPolicy', label: t('monitor.views.monitoringPolicy') },
  ];
}

export function resolveViewModalPublicTabs(input: {
  hasOpsAnalysis: boolean;
  instUuid: string;
  nodeId: string;
  widgets: Partial<Record<AppWidgetKey, boolean>>;
  t: (id: string) => string;
}): ViewModalPublicTabItem[] {
  const canShow = (widgetKey: AppWidgetKey) =>
    canShowCrossModulePublicWidget({
      hostApp: 'monitor',
      widgetKey,
      hasOpsAnalysis: input.hasOpsAnalysis,
      providerDeclared: Boolean(input.widgets[widgetKey]),
    });
  const tabs: ViewModalPublicTabItem[] = [];
  if (input.instUuid && canShow('ops-analysis.relatedTopology')) {
    tabs.push({
      key: 'relatedTopology',
      identifierProp: 'instUuid',
      label: input.t('monitor.views.relatedTopology'),
    });
  }
  if (input.instUuid && canShow('cmdb.baseInfo')) {
    tabs.push({
      key: 'baseInfo',
      identifierProp: 'instUuid',
      label: input.t('monitor.views.assetInfo'),
    });
  }
  if (input.instUuid && canShow('cmdb.assetChange')) {
    tabs.push({
      key: 'assetChange',
      identifierProp: 'instUuid',
      label: input.t('monitor.views.assetChange'),
    });
  }
  if (input.nodeId && canShow('node.nodeStatus')) {
    tabs.push({
      key: 'nodeStatus',
      identifierProp: 'nodeId',
      label: input.t('monitor.views.nodeStatus'),
    });
  }
  return tabs;
}

export function shouldLookupViewModalStableIds(input: {
  hasOpsAnalysis: boolean;
  monitorId: string;
  instUuid: string;
  nodeId: string;
  widgets: Partial<Record<AppWidgetKey, boolean>>;
}): boolean {
  if (!input.hasOpsAnalysis || !input.monitorId.trim()) {
    return false;
  }
  const canShow = (widgetKey: AppWidgetKey) =>
    canShowCrossModulePublicWidget({
      hostApp: 'monitor',
      widgetKey,
      hasOpsAnalysis: input.hasOpsAnalysis,
      providerDeclared: Boolean(input.widgets[widgetKey]),
    });
  const needsInstUuid =
    !input.instUuid &&
    (canShow('ops-analysis.relatedTopology') ||
      canShow('cmdb.baseInfo') ||
      canShow('cmdb.assetChange'));
  const needsNodeId = !input.nodeId && canShow('node.nodeStatus');
  return needsInstUuid || needsNodeId;
}
