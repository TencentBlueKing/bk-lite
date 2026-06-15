export interface PolicyTemplateItem {
  template_key?: string;
  id?: string | number;
  name?: string;
  description?: string;
  metric_name?: string;
  template_group?: string;
  plugin_id?: string | number;
  plugin_display_name?: string;
  plugin_name?: string;
  [key: string]: any;
}

export interface TemplateGroup {
  name: string;
  templates: PolicyTemplateItem[];
  selectedCount: number;
}

export interface BulkAssetItem {
  instance_id: string;
  instance_name?: string;
  organization?: number[] | string[] | number | string;
  plugins?: Array<{ id?: string | number; name?: string; display_name?: string }>;
  [key: string]: any;
}

export interface BulkConfig {
  name_prefix?: string;
  enable?: boolean;
  schedule?: { type: string; value: number };
  period?: { type: string; value: number };
  notice?: boolean;
  notice_type_ids?: Array<string | number>;
  notice_users?: string[];
  [key: string]: any;
}

export interface PolicyPreviewItem {
  key: string;
  name: string;
  metricLabel: string;
  statusLabel: string;
}

export const getTemplateKey = (template: PolicyTemplateItem): string =>
  String(template.template_key ?? template.id ?? template.name ?? template.metric_name);

export const displayAssetName = (asset: BulkAssetItem): string => {
  if (asset.instance_name) return asset.instance_name;
  const match = asset.instance_id.match(/^\('([^']*)',?\)$/);
  return match?.[1] || asset.instance_id;
};

const getTemplateGroupName = (template: PolicyTemplateItem): string =>
  template.template_group ||
  template.plugin_display_name ||
  template.plugin_name ||
  String(template.plugin_id || '--');

export const getMetricLabel = (template: PolicyTemplateItem): string =>
  `${template.plugin_display_name || template.plugin_name || template.plugin_id || '--'} - ${template.metric_name || '--'}`;

export const groupPolicyTemplates = (
  templates: PolicyTemplateItem[],
  selectedKeys: string[] = []
): TemplateGroup[] => {
  const selectedSet = new Set(selectedKeys);
  const groupMap = new Map<string, PolicyTemplateItem[]>();
  templates.forEach((template) => {
    const groupName = getTemplateGroupName(template);
    const list = groupMap.get(groupName) || [];
    list.push(template);
    groupMap.set(groupName, list);
  });

  return Array.from(groupMap.entries()).map(([name, list]) => ({
    name,
    templates: list,
    selectedCount: list.filter((item) => selectedSet.has(getTemplateKey(item))).length,
  }));
};

export const toggleTemplateSelection = (
  selectedKeys: string[],
  template: PolicyTemplateItem
): string[] => {
  const key = getTemplateKey(template);
  return selectedKeys.includes(key)
    ? selectedKeys.filter((item) => item !== key)
    : [...selectedKeys, key];
};

export const selectTemplateGroup = (
  selectedKeys: string[],
  groupTemplates: PolicyTemplateItem[],
  checked: boolean
): string[] => {
  const keys = groupTemplates.map(getTemplateKey);
  if (!checked) {
    return selectedKeys.filter((key) => !keys.includes(key));
  }
  return Array.from(new Set([...selectedKeys, ...keys]));
};

export const clearTemplateSelection = (): string[] => [];

export const buildPolicyPreview = (
  templates: PolicyTemplateItem[],
  assets: BulkAssetItem[],
  config: BulkConfig
): PolicyPreviewItem[] => {
  const prefix = (config.name_prefix || '').trim();
  return templates.flatMap((template) =>
    assets.map((asset) => {
      const assetName = displayAssetName(asset);
      const policyName = [prefix, template.name, assetName].filter(Boolean).join('-');
      return {
        key: `${getTemplateKey(template)}:${asset.instance_id}`,
        name: policyName,
        metricLabel: getMetricLabel(template),
        statusLabel: config.enable === false ? '停用' : '启用',
      };
    })
  );
};

export const buildBulkApplyPayload = ({
  monitorObjectId,
  templates,
  assets,
  config,
}: {
  monitorObjectId: string | number;
  templates: PolicyTemplateItem[];
  assets: BulkAssetItem[];
  config: BulkConfig;
}) => ({
  monitor_object: monitorObjectId,
  templates: templates.map((template) => ({
    ...template,
    collect_type: template.plugin_id ?? template.collect_type,
  })),
  asset_ids: assets.map((asset) => asset.instance_id),
  config,
});
