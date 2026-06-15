import type { PluginItem } from '@/app/monitor/types/integration';

export type PluginConfigContentState =
  | 'none'
  | 'reportedOnly'
  | 'missingConfig'
  | 'configured';

export const isSameTemplatePlugin = (
  currentPlugin: PluginItem | null,
  nextPlugin: PluginItem | null
) => {
  if (!currentPlugin || !nextPlugin) return false;

  if (currentPlugin.plugin_id && nextPlugin.plugin_id) {
    return currentPlugin.plugin_id === nextPlugin.plugin_id;
  }

  return (
    currentPlugin.name === nextPlugin.name &&
    currentPlugin.collector === nextPlugin.collector &&
    currentPlugin.collect_type === nextPlugin.collect_type
  );
};

export const isPluginConfigurable = (plugin: PluginItem | null) => {
  if (!plugin) return false;
  if (plugin.configured === false || plugin.config_source === 'reported_only') {
    return false;
  }
  if (plugin.configured === true) {
    return true;
  }
  return plugin.collect_mode !== 'manual';
};

export const getPluginConfigFetchDecision = (
  currentPlugin: PluginItem | null,
  nextPlugin: PluginItem
) => {
  const shouldChangeSelection = !isSameTemplatePlugin(currentPlugin, nextPlugin);
  return {
    shouldChangeSelection,
    shouldFetchConfig: shouldChangeSelection && isPluginConfigurable(nextPlugin)
  };
};

export const getPluginConfigContentState = (
  plugin: PluginItem | null,
  configList: unknown[]
): PluginConfigContentState => {
  if (!plugin) return 'none';
  if (!isPluginConfigurable(plugin)) return 'reportedOnly';
  return configList.length ? 'configured' : 'missingConfig';
};
