import type { PluginItem } from '@/app/monitor/types/integration';

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

export const getPluginConfigFetchDecision = (
  currentPlugin: PluginItem | null,
  nextPlugin: PluginItem
) => {
  const shouldChangeSelection = !isSameTemplatePlugin(currentPlugin, nextPlugin);
  return {
    shouldChangeSelection,
    shouldFetchConfig: shouldChangeSelection && nextPlugin.collect_mode !== 'manual'
  };
};
