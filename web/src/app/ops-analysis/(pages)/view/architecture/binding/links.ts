import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import { encodeInstanceIdValuesParam } from '@/app/monitor/dashboards/shared/utils/instance';
import { withDashboardReturnContext } from '@/app/monitor/dashboards/shared/utils/return-navigation';
import { resolveDashboardUrl } from '@/app/monitor/dashboards/shared/utils/flow-dashboard-route';

export interface MonitorDetailLinkInput {
  monitorObjectId: string;
  name: string;
  displayName: string;
  icon?: string;
  instanceId: string;
  instanceName: string;
  instanceIdValues: string[];
  instanceIdKeys: string[];
  plugins?: Array<{ collect_type?: string; name?: string }>;
}

export function buildCmdbDetailHref(input: {
  modelId: string;
  instUuid: string;
  instName: string;
}): string {
  const params = new URLSearchParams({
    model_id: input.modelId,
    inst_uuid: input.instUuid,
    inst_name: input.instName,
  });
  return `/cmdb/assetData/detail/baseInfo?${params.toString()}`;
}

export function buildAlarmHref(monitorId: string): string {
  return `/alarm/alarms?${new URLSearchParams({ resource_id: monitorId }).toString()}`;
}

export function buildMonitorDetailHref(input: MonitorDetailLinkInput): string {
  const params = new URLSearchParams({
    monitorObjId: input.monitorObjectId,
    name: input.name,
    monitorObjDisplayName: input.displayName,
    icon: input.icon || OBJECT_DEFAULT_ICON,
    instance_id: input.instanceId,
    instance_name: input.instanceName,
    instance_id_values: encodeInstanceIdValuesParam(input.instanceIdValues),
    instance_id_keys: input.instanceIdKeys.length ? input.instanceIdKeys.join(',') : 'instance_id',
  });
  const withReturn = withDashboardReturnContext(params, {
    objectId: input.monitorObjectId,
    objectName: input.displayName || input.name,
  });
  const professional = resolveDashboardUrl({
    monitorObjectName: input.name,
    monitorObjectDisplayName: input.displayName,
    instancePlugins: input.plugins,
    queryString: withReturn.toString(),
  });
  return professional || `/monitor/view/detail?${withReturn.toString()}`;
}

/** collect_type is read from the monitor effective_plugins payload on the architecture side. */
export interface ArchitectureEffectivePlugin {
  collect_type?: string;
  name?: string;
}

export function readArchitectureEffectivePlugins(raw: unknown): ArchitectureEffectivePlugin[] {
  if (!Array.isArray(raw)) return [];
  const plugins: ArchitectureEffectivePlugin[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const record = item as Record<string, unknown>;
    const plugin: ArchitectureEffectivePlugin = {};
    if (typeof record.collect_type === 'string') plugin.collect_type = record.collect_type;
    if (typeof record.name === 'string') plugin.name = record.name;
    plugins.push(plugin);
  }
  return plugins;
}

export interface MonitorLinkContext {
  monitorObject?: unknown;
  monitorName: string;
  objects?: Array<{ display_name?: string; icon?: string }>;
  form?: {
    instance_id?: string;
    instance_name?: string;
    instance_id_values?: string[];
    instance_id_keys?: string[];
  };
  linkPlugins?: Array<{ collect_type?: string; name?: string }>;
}

/** Empty when the monitor instance was not resolved, so the tab hides the button. */
export function buildMonitorHrefFromContext(context: MonitorLinkContext | null): string {
  const instanceId = context?.form?.instance_id?.trim() || '';
  const rawObject = context?.monitorObject;
  const monitorObjectId = typeof rawObject === 'string' || typeof rawObject === 'number' || typeof rawObject === 'bigint'
    ? String(rawObject).trim()
    : '';
  if (!context || !instanceId || !monitorObjectId) return '';
  const object = context.objects?.[0];
  const values = context.form?.instance_id_values?.filter((value) => value.trim()) ?? [];
  const keys = context.form?.instance_id_keys?.filter((value) => value.trim()) ?? [];
  return buildMonitorDetailHref({
    monitorObjectId,
    name: context.monitorName,
    displayName: object?.display_name || context.monitorName,
    icon: object?.icon,
    instanceId,
    instanceName: context.form?.instance_name?.trim() || instanceId,
    instanceIdValues: values.length ? values : [instanceId],
    instanceIdKeys: keys.length ? keys : ['instance_id'],
    plugins: context.linkPlugins,
  });
}
