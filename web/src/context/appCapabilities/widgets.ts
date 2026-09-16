import type { AppCapabilityName } from './catalog';

export const APP_WIDGET_KEYS = [
  'monitor.monitorView',
  'monitor.alertList',
  'monitor.monitorPolicy',
  'cmdb.baseInfo',
  'cmdb.assetChange',
  'ops-analysis.relatedTopology',
  'ops-analysis.networkStatusTopology',
  'ops-analysis.application3D',
  'ops-analysis.room3D',
  'log.alertRawLog',
  'node.nodeStatus',
  'apm.serviceOverview',
  'apm.callChain',
] as const;

export type AppWidgetKey = (typeof APP_WIDGET_KEYS)[number];

export type AppWidgetLoader = () => Promise<{ default: unknown }>;

const APP_WIDGET_APP: Record<AppWidgetKey, AppCapabilityName> = {
  'monitor.monitorView': 'monitor',
  'monitor.alertList': 'monitor',
  'monitor.monitorPolicy': 'monitor',
  'cmdb.baseInfo': 'cmdb',
  'cmdb.assetChange': 'cmdb',
  'ops-analysis.relatedTopology': 'ops-analysis',
  'ops-analysis.networkStatusTopology': 'ops-analysis',
  'ops-analysis.application3D': 'ops-analysis',
  'ops-analysis.room3D': 'ops-analysis',
  'log.alertRawLog': 'log',
  'node.nodeStatus': 'node',
  'apm.serviceOverview': 'apm',
  'apm.callChain': 'apm',
};

export const appNameForWidgetKey = (key: AppWidgetKey): AppCapabilityName =>
  APP_WIDGET_APP[key];

export const resolveWidgetLoader = (
  api: unknown,
  key: AppWidgetKey,
): AppWidgetLoader | null => {
  if (!api || typeof api !== 'object') {
    return null;
  }
  const widgets = (api as { widgets?: Record<string, unknown> }).widgets;
  const loader = widgets?.[key];
  return typeof loader === 'function' ? (loader as AppWidgetLoader) : null;
};
