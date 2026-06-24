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
  organization?: number[] | string[] | number | string | Record<string, any>;
  organizations?: number[] | string[] | number | string | Record<string, any>;
  plugins?: Array<{ id?: string | number; name?: string; display_name?: string }>;
  [key: string]: any;
}

export interface BulkConfig {
  name_prefix?: string;
  enable?: boolean;
  schedule?: { type: string; value: number };
  period?: { type: string; value: number };
  notice?: boolean;
  notice_type?: string;
  notice_type_ids?: Array<string | number>;
  notice_users?: string[];
  enable_alerts?: string[];
  no_data_enabled?: boolean;
  no_data_period?: { type: string; value: number };
  no_data_recovery_period?: { type: string; value: number };
  no_data_level?: string;
  no_data_alert_name?: string;
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

export const getPrimaryNoticeType = (
  noticeTypeIds: Array<string | number> = [],
  channels: Array<{ id: string | number; channel_type?: string }> = []
): string => {
  const firstId = noticeTypeIds[0];
  if (firstId === undefined) return '';
  const channel = channels.find((item) => item.id === firstId);
  return channel?.channel_type || '';
};

export const normalizeBulkConfig = (
  config: BulkConfig,
  channels: Array<{ id: string | number; channel_type?: string }> = []
): BulkConfig => {
  const enableAlerts = new Set(config.enable_alerts || ['threshold']);
  enableAlerts.add('threshold');

  const noDataEnabled = Boolean(config.no_data_enabled);
  if (noDataEnabled) {
    enableAlerts.add('no_data');
  } else {
    enableAlerts.delete('no_data');
  }

  const noticeTypeIds = config.notice_type_ids || [];
  const normalized: BulkConfig = {
    ...config,
    enable_alerts: Array.from(enableAlerts),
    notice_type: getPrimaryNoticeType(noticeTypeIds, channels),
  };

  if (!normalized.notice) {
    normalized.notice_type = '';
    normalized.notice_type_ids = [];
    normalized.notice_users = [];
  }

  if (noDataEnabled) {
    const noDataPeriod = config.no_data_period || { type: 'min', value: 5 };
    normalized.no_data_period = noDataPeriod;
    normalized.no_data_recovery_period = config.no_data_recovery_period || noDataPeriod;
    normalized.no_data_level = config.no_data_level || 'warning';
    normalized.no_data_alert_name = config.no_data_alert_name || '无数据告警';
  } else {
    delete normalized.no_data_period;
    delete normalized.no_data_recovery_period;
    delete normalized.no_data_level;
    delete normalized.no_data_alert_name;
  }

  return normalized;
};

interface OrganizationOption {
  value?: string | number;
  label?: string;
  name?: string;
  children?: OrganizationOption[];
}

const findOrganizationLabel = (
  organizations: OrganizationOption[],
  value: string | number
): string | null => {
  const valueText = String(value);
  for (const organization of organizations) {
    if (String(organization.value) === valueText) {
      return organization.label || organization.name || null;
    }
    const childLabel = findOrganizationLabel(organization.children || [], value);
    if (childLabel) return childLabel;
  }
  return null;
};

export const getAssetOrganizationText = (
  asset: Pick<BulkAssetItem, 'organization' | 'organizations'>,
  organizations: OrganizationOption[] = []
): string => {
  const organization = asset.organization || asset.organizations;
  if (!organization) return '--';
  const values = Array.isArray(organization) ? organization : [organization];
  const labels = values
    .map((item) => {
      if (typeof item === 'object' && item !== null) {
        return item.name || item.label;
      }
      return findOrganizationLabel(organizations, item) || String(item);
    })
    .filter(Boolean);
  return labels.length ? labels.join(',') : '--';
};

export const getAssetCollectionTemplateLabels = (
  asset: Pick<BulkAssetItem, 'plugins'>
): string[] => {
  return (asset.plugins || [])
    .map((plugin) => plugin.display_name || plugin.name || plugin.id)
    .filter((label): label is string | number => label !== undefined && label !== null)
    .map(String);
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
