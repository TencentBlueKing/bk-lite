import { getProfessionalDashboardKey } from '../../metadata';
import type { FlowProtocol } from '../../objects/flow-common/constants';
import { isFlowSupportedObjectName } from '../../objects/flow-common/constants';
import { isFlowCollectType, type FlowDashboardPlugin } from './flow-dashboard-route';
import { preserveDashboardDisplayMode } from './display-mode-route';

export type FlowViewKind = 'snmp' | FlowProtocol;

export const FLOW_VIEW_SWITCH_ROUTE_KEYS = new Set([
  'switch',
  'router',
  'firewall',
  'loadbalance',
  'netflow',
  'sflow',
]);

export const FLOW_VIEW_LABELS: Record<FlowViewKind, string> = {
  snmp: 'SNMP 监控',
  netflow: 'NetFlow 流量',
  sflow: 'sFlow 流量',
};

export const isSnmpCollectType = (collectType?: string | null): boolean =>
  String(collectType || '')
    .trim()
    .toLowerCase()
    .startsWith('snmp');

export const isSnmpPlugin = (plugin: FlowDashboardPlugin): boolean => {
  if (isSnmpCollectType(plugin.collect_type)) return true;
  return String(plugin.name || '')
    .trim()
    .toUpperCase()
    .includes('SNMP');
};

export const pluginMatchesFlowView = (
  plugin: FlowDashboardPlugin,
  view: FlowViewKind,
): boolean => {
  if (view === 'snmp') return isSnmpPlugin(plugin);
  return String(plugin.collect_type || '').trim() === view;
};

export const filterPluginsByFlowView = <T extends FlowDashboardPlugin>(
  plugins: T[],
  view: FlowViewKind | null | undefined,
): T[] => {
  if (!view) return plugins;
  return plugins.filter((plugin) => pluginMatchesFlowView(plugin, view));
};

export const getAvailableFlowViews = (
  plugins?: FlowDashboardPlugin[] | null,
): FlowViewKind[] => {
  const list = plugins || [];
  const views: FlowViewKind[] = [];

  if (list.some(isSnmpPlugin)) views.push('snmp');
  if (list.some((plugin) => String(plugin.collect_type || '').trim() === 'netflow')) {
    views.push('netflow');
  }
  if (list.some((plugin) => String(plugin.collect_type || '').trim() === 'sflow')) {
    views.push('sflow');
  }

  return views;
};

export const resolveCurrentFlowView = (routeKey?: string | null): FlowViewKind | null => {
  const normalized = String(routeKey || '').trim();
  if (isFlowCollectType(normalized)) return normalized;
  if (['switch', 'router', 'firewall', 'loadbalance'].includes(normalized)) return 'snmp';
  return null;
};

/** NetFlow/sFlow 专业盘路由本身即 Flow 语境；SNMP 盘需可识别的网络对象名。 */
export const isFlowViewSwitchContext = (
  routeKey?: string | null,
  monitorObjectName?: string | null,
): boolean => {
  const normalizedRoute = String(routeKey || '').trim();
  if (!FLOW_VIEW_SWITCH_ROUTE_KEYS.has(normalizedRoute)) return false;
  if (normalizedRoute === 'netflow' || normalizedRoute === 'sflow') return true;
  return isFlowSupportedObjectName(monitorObjectName);
};

/** 全量指标区按路由预选插件页签（与 FlowViewSwitch 路由语义一致）。 */
export const resolvePreferredCollectTypeFromRoute = (
  routeKey?: string | null,
): 'snmp' | FlowProtocol | null => {
  const normalized = String(routeKey || '').trim();
  if (normalized === 'netflow' || normalized === 'sflow') return normalized;
  if (['switch', 'router', 'firewall', 'loadbalance'].includes(normalized)) return 'snmp';
  return null;
};

export const resolveFlowViewRouteKey = (
  view: FlowViewKind,
  monitorObjectName?: string | null,
): string | null => {
  if (view === 'netflow' || view === 'sflow') return view;
  return getProfessionalDashboardKey(monitorObjectName) || null;
};

export const buildFlowViewSwitchUrl = (
  view: FlowViewKind,
  options: {
    monitorObjectName?: string | null;
    searchParams: URLSearchParams;
  },
): string | null => {
  const routeKey = resolveFlowViewRouteKey(view, options.monitorObjectName);
  if (!routeKey) return null;

  const params = preserveDashboardDisplayMode(
    new URLSearchParams(options.searchParams.toString()),
    options.searchParams,
  );

  return `/monitor/view/dashboard/${routeKey}?${params.toString()}`;
};

export const shouldShowFlowViewSwitch = (options: {
  routeKey?: string | null;
  monitorObjectName?: string | null;
  availableViews: FlowViewKind[];
}): boolean => {
  if (!isFlowViewSwitchContext(options.routeKey, options.monitorObjectName)) return false;
  return options.availableViews.length >= 2;
};
