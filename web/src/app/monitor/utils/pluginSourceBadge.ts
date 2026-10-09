export const CUSTOM_PLUGIN_TEMPLATE_TYPES = [
  'api',
  'pull',
  'snmp',
  'script'
] as const;

export type CustomPluginTemplateType =
  (typeof CUSTOM_PLUGIN_TEMPLATE_TYPES)[number];

export type PluginPackSourceKind = 'none' | 'builtin' | 'pinned';

export interface PluginSourceMarkers {
  is_built_in?: boolean;
  is_custom?: boolean;
  is_pre?: boolean;
  template_type?: string | null;
  pack_version?: string | null;
}

export interface PluginSourceBadge {
  showSelfBuilt: boolean;
  showPackTag: boolean;
  packKind: PluginPackSourceKind;
  packVersion: string;
}

const CUSTOM_TEMPLATE_TYPE_SET = new Set<string>(CUSTOM_PLUGIN_TEMPLATE_TYPES);

const toNonEmpty = (value?: string | null): string =>
  typeof value === 'string' && value.trim() ? value.trim() : '';

export function isCustomPluginTemplate(
  plugin: Pick<PluginSourceMarkers, 'is_custom' | 'template_type'>
): boolean {
  if (plugin.is_custom === true) {
    return true;
  }
  return CUSTOM_TEMPLATE_TYPE_SET.has(toNonEmpty(plugin.template_type));
}

export function isBuiltInPlugin(plugin: PluginSourceMarkers): boolean {
  if (isCustomPluginTemplate(plugin)) {
    return false;
  }
  if (plugin.is_built_in === false || plugin.is_pre === false) {
    return false;
  }
  if (plugin.is_built_in === true || plugin.is_pre === true) {
    return true;
  }
  const templateType = toNonEmpty(plugin.template_type);
  return !templateType || templateType === 'builtin';
}

export function resolvePluginSourceBadge(
  plugin: PluginSourceMarkers
): PluginSourceBadge {
  const packVersion = toNonEmpty(plugin.pack_version);
  if (isCustomPluginTemplate(plugin)) {
    return {
      showSelfBuilt: true,
      showPackTag: false,
      packKind: 'none',
      packVersion: ''
    };
  }
  if (packVersion) {
    return {
      showSelfBuilt: false,
      showPackTag: true,
      packKind: 'pinned',
      packVersion
    };
  }
  if (isBuiltInPlugin(plugin)) {
    return {
      showSelfBuilt: false,
      showPackTag: true,
      packKind: 'builtin',
      packVersion: ''
    };
  }
  return {
    showSelfBuilt: false,
    showPackTag: false,
    packKind: 'none',
    packVersion: ''
  };
}
