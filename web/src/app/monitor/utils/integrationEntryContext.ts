import { findByMonitorId, toMonitorIdString } from './monitorIds';

export interface IntegrationEntryPlugin {
  id?: unknown;
  name?: unknown;
  display_name?: unknown;
  display_description?: unknown;
  template_type?: unknown;
  parent_monitor_object?: unknown;
  parent_monitor_object_name?: unknown;
  parent_monitor_object_icon?: unknown;
}

export interface IntegrationEntryObject {
  id?: unknown;
  name?: unknown;
  icon?: unknown;
}

export interface IntegrationEntryContext {
  objectId: string;
  objectName: string;
  objectIcon: string;
  pluginId: string;
  pluginName: string;
  pluginDisplayName: string;
  pluginDescription: string;
  templateType: string;
}

export type IntegrationEntryContextResult =
  | { ok: true; context: IntegrationEntryContext }
  | { ok: false; reason: 'missing-parent-object' | 'invalid-plugin' };

const toNonEmptyString = (value: unknown): string =>
  typeof value === 'string' && value.trim() ? value.trim() : '';

export const parseIntegrationObjectId = (value: unknown): number | undefined => {
  const normalized = toMonitorIdString(value);
  if (!/^\d+$/.test(normalized)) return undefined;
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : undefined;
};

export const resolveIntegrationEntryContext = (
  plugin: IntegrationEntryPlugin,
  monitorObjects: IntegrationEntryObject[]
): IntegrationEntryContextResult => {
  const pluginId = toMonitorIdString(plugin.id);
  const pluginName = toNonEmptyString(plugin.name);
  if (!pluginId || !pluginName) {
    return { ok: false, reason: 'invalid-plugin' };
  }

  const objectId = toMonitorIdString(plugin.parent_monitor_object);
  if (!objectId) {
    return { ok: false, reason: 'missing-parent-object' };
  }

  const relatedObject = findByMonitorId(monitorObjects, objectId);
  const objectName =
    toNonEmptyString(plugin.parent_monitor_object_name) ||
    toNonEmptyString(relatedObject?.name);
  if (!objectName || !parseIntegrationObjectId(objectId)) {
    return { ok: false, reason: 'missing-parent-object' };
  }

  return {
    ok: true,
    context: {
      objectId,
      objectName,
      objectIcon:
        toNonEmptyString(plugin.parent_monitor_object_icon) ||
        toNonEmptyString(relatedObject?.icon),
      pluginId,
      pluginName,
      pluginDisplayName: toNonEmptyString(plugin.display_name),
      pluginDescription: toNonEmptyString(plugin.display_description),
      templateType: toNonEmptyString(plugin.template_type)
    }
  };
};

export const buildIntegrationConfigureUrl = (
  context: IntegrationEntryContext,
  defaultIcon: string
): string => {
  const params = new URLSearchParams({
    id: context.objectId,
    icon: context.objectIcon || defaultIcon,
    name: context.objectName,
    plugin_name: context.pluginName,
    plugin_id: context.pluginId,
    template_type: context.templateType,
    plugin_display_name: context.pluginDisplayName,
    plugin_description: context.pluginDescription || '--'
  });
  return `/monitor/integration/list/detail/configure?${params.toString()}`;
};
