import { LEVEL_MAP } from '@/app/monitor/constants';

export interface PolicyTemplateItem {
  template_key?: string;
  id?: string | number;
  name?: string;
  description?: string;
  metric_name?: string;
  metric_unit?: string;
  threshold_unit?: string;
  calculation_unit?: string;
  trigger_count?: number;
  threshold?: Array<{
    level?: string;
    method?: string;
    value?: string | number | null;
  }>;
  algorithm?: string;
  group_algorithm?: string;
  query_condition?: {
    type?: string;
    metric_name?: string;
    result_name?: string;
    expression?: string;
    queries?: Array<{ ref?: string; metric_name?: string }>;
    [key: string]: unknown;
  };
  template_group?: string;
  plugin_id?: string | number;
  plugin_display_name?: string;
  plugin_name?: string;
  template_type?: 'builtin' | 'custom';
  deletable?: boolean;
  [key: string]: unknown;
}

export interface TemplateGroup {
  name: string;
  templates: PolicyTemplateItem[];
  selectedCount: number;
}

export interface BulkAssetItem {
  instance_id: string;
  instance_name?: string;
  organization?: number[] | string[] | number | string | Record<string, unknown>;
  organizations?: number[] | string[] | number | string | Record<string, unknown>;
  plugins?: Array<{ id?: string | number; name?: string; display_name?: string }>;
  [key: string]: unknown;
}

export interface BulkAssetSelectionState {
  selectedAssetIds: string[];
  selectedAssets: BulkAssetItem[];
}

export interface BulkAssetPaginationState {
  current: number;
  pageSize: number;
  total: number;
}

export interface BulkConfig {
  name_prefix?: string;
  enable?: boolean;
  schedule?: { type: string; value: number };
  period?: { type: string; value: number };
  trigger_count?: number;
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
  [key: string]: unknown;
}

export interface PolicyPreviewItem {
  key: string;
  name: string;
  metricLabel: string;
  assetScopeLabel: string;
  statusLabel: string;
  statusEnabled: boolean;
}

const LEVEL_ORDER = ['critical', 'error', 'warning'] as const;

const LEVEL_LABELS: Record<string, string> = {
  critical: '严重',
  error: '错误',
  warning: '警告',
};

export interface TemplateThresholdItem {
  level: string;
  label: string;
  method: string;
  value: string | number;
  unitSuffix: string;
  color: string;
}

export const getTemplateThresholdItems = (
  template: PolicyTemplateItem
): TemplateThresholdItem[] => {
  const thresholds = Array.isArray(template.threshold) ? template.threshold : [];
  const unitSuffix = formatUnitSuffix(
    String(template.threshold_unit || template.calculation_unit || template.metric_unit || '')
  );

  return thresholds
    .filter(
      (item) =>
        item?.value !== null &&
        item?.value !== undefined &&
        item?.value !== ''
    )
    .sort((left, right) => {
      const leftIndex = LEVEL_ORDER.indexOf(
        left.level as (typeof LEVEL_ORDER)[number]
      );
      const rightIndex = LEVEL_ORDER.indexOf(
        right.level as (typeof LEVEL_ORDER)[number]
      );
      return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex);
    })
    .map((item) => ({
      level: item.level,
      label: LEVEL_LABELS[item.level] || item.level,
      method: METHOD_LABELS[item.method] || item.method || '>',
      value: item.value,
      unitSuffix,
      color:
        (LEVEL_MAP[item.level as keyof typeof LEVEL_MAP] as string) ||
        'var(--color-text-3)',
    }));
};

const METHOD_LABELS: Record<string, string> = {
  '>': '>',
  '<': '<',
  '=': '=',
  '!=': '≠',
  '>=': '≥',
  '<=': '≤',
};

const ALGORITHM_LABELS: Record<string, string> = {
  avg_over_time: 'AVG_OVER_TIME',
  max_over_time: 'MAX_OVER_TIME',
  min_over_time: 'MIN_OVER_TIME',
  sum_over_time: 'SUM_OVER_TIME',
  count_over_time: 'COUNT_OVER_TIME',
  last_over_time: 'LAST_OVER_TIME',
};

const GROUP_ALGORITHM_LABELS: Record<string, string> = {
  avg: 'AVG',
  max: 'MAX',
  min: 'MIN',
  sum: 'SUM',
  count: 'COUNT',
};

const formatUnitSuffix = (unit?: string | null): string => {
  if (!unit || unit === 'none' || unit === 'short') return '';
  if (unit === 'percent' || unit === '%') return '%';
  return unit;
};

export const formatTemplateAlgorithmSummary = (template: PolicyTemplateItem): string => {
  const groupAlgorithm = template.group_algorithm
    ? GROUP_ALGORITHM_LABELS[String(template.group_algorithm).toLowerCase()] ||
      String(template.group_algorithm).toUpperCase()
    : '';
  const algorithm = template.algorithm
    ? ALGORITHM_LABELS[String(template.algorithm).toLowerCase()] ||
      String(template.algorithm).toUpperCase()
    : '';
  if (groupAlgorithm && algorithm) return `${groupAlgorithm} / ${algorithm}`;
  return groupAlgorithm || algorithm || '';
};

export const getTemplateTriggerCount = (
  template: PolicyTemplateItem,
  triggerCount?: number
): number => {
  if (typeof triggerCount === 'number') return triggerCount;
  return typeof template.trigger_count === 'number' ? template.trigger_count : 1;
};

export const getTemplateKey = (template: PolicyTemplateItem): string => {
  if (template.template_key) return String(template.template_key);
  if (template.id !== undefined && template.id !== null && template.id !== '') {
    return String(template.id);
  }
  return [template.plugin_id || '', template.name || '', template.metric_name || '']
    .join(':');
};

export const displayAssetName = (asset: BulkAssetItem): string => {
  if (asset.instance_name) return asset.instance_name;
  const match = asset.instance_id.match(/^\('([^']*)',?\)$/);
  return match?.[1] || asset.instance_id;
};

export const reconcileBulkAssetSelection = (
  previousSelectedAssets: BulkAssetItem[],
  visibleAssets: BulkAssetItem[],
  selectedAssetIds: string[]
): BulkAssetSelectionState => {
  const selectedIdSet = new Set(selectedAssetIds);
  const selectedAssetMap = new Map(
    previousSelectedAssets
      .filter((asset) => selectedIdSet.has(asset.instance_id))
      .map((asset) => [asset.instance_id, asset])
  );

  visibleAssets.forEach((asset) => {
    if (selectedIdSet.has(asset.instance_id)) {
      selectedAssetMap.set(asset.instance_id, asset);
    }
  });

  return {
    selectedAssetIds,
    selectedAssets: selectedAssetIds
      .map((instanceId) => selectedAssetMap.get(instanceId))
      .filter((asset): asset is BulkAssetItem => Boolean(asset)),
  };
};

export const changeBulkAssetPage = (
  pagination: BulkAssetPaginationState,
  page: number,
  pageSize: number
): BulkAssetPaginationState => ({
  ...pagination,
  current: pageSize === pagination.pageSize ? page : 1,
  pageSize,
});

export const resetBulkAssetPageForSearch = (
  pagination: BulkAssetPaginationState
): BulkAssetPaginationState => ({
  ...pagination,
  current: 1,
});

const getTemplateGroupName = (template: PolicyTemplateItem): string =>
  template.template_group ||
  template.plugin_display_name ||
  template.plugin_name ||
  String(template.plugin_id || '--');

export const getTemplateMetricName = (template: PolicyTemplateItem): string =>
  String(template.metric_name || template.query_condition?.metric_name || '').trim();

export const formatTemplateListName = (
  template: PolicyTemplateItem,
  siblings: PolicyTemplateItem[] = []
): string => {
  const name = String(template.name || '').trim() || '--';
  const sameNameCount = siblings.filter(
    (item) => String(item.name || '').trim() === String(template.name || '').trim()
  ).length;
  if (sameNameCount <= 1) return name;
  const metric = getTemplateMetricName(template);
  const plugin = String(
    template.plugin_display_name || template.plugin_name || template.plugin_id || ''
  ).trim();
  const suffix =
    metric ||
    plugin ||
    (template.id !== undefined && template.id !== null && template.id !== ''
      ? `ID ${template.id}`
      : '');
  return suffix ? `${name}（${suffix}）` : name;
};

export const buildDistinctPolicyNames = (
  templates: PolicyTemplateItem[],
  namePrefix = ''
): string[] => {
  const prefix = namePrefix.trim();
  const bases = templates.map((template) => {
    const metric = getTemplateMetricName(template);
    const templateName = String(template.name || metric || '').trim();
    return [prefix, templateName].filter(Boolean).join('-') || metric || '策略';
  });
  const baseCounts = bases.reduce<Record<string, number>>((counts, base) => {
    counts[base] = (counts[base] || 0) + 1;
    return counts;
  }, {});
  const used = new Set<string>();
  return templates.map((template, index) => {
    let name = bases[index];
    const metric = getTemplateMetricName(template);
    const templateName = String(template.name || metric || '').trim();
    if (baseCounts[bases[index]] > 1 && metric && metric !== templateName) {
      name = `${name}-${metric}`;
    }
    let candidate = name;
    let suffix = 2;
    while (used.has(candidate)) {
      candidate = `${name}-${suffix}`;
      suffix += 1;
    }
    used.add(candidate);
    return candidate;
  });
};

export const getMetricLabel = (template: PolicyTemplateItem): string =>
  `${template.plugin_display_name || template.plugin_name || template.plugin_id || '--'} - ${getTemplateMetricName(template) || '--'}`;

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

export const containsBuiltinTemplate = (
  templates: PolicyTemplateItem[]
): boolean => templates.some(
  (item) => item.template_type === 'builtin' || item.deletable === false
);

export const canDeleteTemplates = (
  templates: PolicyTemplateItem[]
): boolean => templates.length > 0 && !containsBuiltinTemplate(templates);

type TranslateFn = (
  id: string,
  defaultMessage?: string,
  values?: Record<string, string | number>
) => string;

export const buildAssetScopeLabel = (
  assets: BulkAssetItem[],
  t?: TranslateFn
): string => {
  if (!assets.length) return '--';
  const assetNames = assets.map(displayAssetName);
  const previewNames = assetNames.slice(0, 3).join('、');
  if (assetNames.length <= 3) {
    return t
      ? t('monitor.events.coverInstances', '覆盖 {count} 个实例：{names}', {
        count: assetNames.length,
        names: previewNames,
      })
      : `覆盖 ${assetNames.length} 个实例：${assetNames.join('、')}`;
  }
  return t
    ? t('monitor.events.coverInstancesMore', '覆盖 {count} 个实例：{names} 等', {
      count: assetNames.length,
      names: previewNames,
    })
    : `覆盖 ${assetNames.length} 个实例：${previewNames} 等`;
};

export const buildPolicyPreview = (
  templates: PolicyTemplateItem[],
  assets: BulkAssetItem[],
  config: BulkConfig,
  t?: TranslateFn
): PolicyPreviewItem[] => {
  const prefix = (config.name_prefix || '').trim();
  const assetScopeLabel = buildAssetScopeLabel(assets, t);
  const policyNames = buildDistinctPolicyNames(templates, prefix);
  const enabledLabel = t ? t('common.enable', '启用') : '启用';
  const disabledLabel = t ? t('monitor.events.inactive', '停用') : '停用';
  return templates.map((template, index) => ({
    key: getTemplateKey(template),
    name: policyNames[index],
    metricLabel: getMetricLabel(template),
    assetScopeLabel,
    statusLabel: config.enable === false ? disabledLabel : enabledLabel,
    statusEnabled: config.enable !== false,
  }));
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
    trigger_count: config.trigger_count || 1,
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

export const COLLECTION_POLICY_BULK_CONFIG_DEFAULTS: BulkConfig = {
  name_prefix: '',
  enable: true,
  schedule: { type: 'min', value: 5 },
  period: { type: 'min', value: 5 },
  trigger_count: 1,
  notice: false,
  notice_type: '',
  notice_type_ids: [],
  notice_users: [],
  enable_alerts: ['threshold'],
  no_data_enabled: false,
};

export const buildCollectionPolicyBulkConfig = (): BulkConfig =>
  normalizeBulkConfig({ ...COLLECTION_POLICY_BULK_CONFIG_DEFAULTS });

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
      if (typeof item === 'string' || typeof item === 'number') {
        return findOrganizationLabel(organizations, item) || String(item);
      }
      if (item && typeof item === 'object') {
        const record = item as Record<string, unknown>;
        return String(record.name || record.label || '');
      }
      return '';
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
  template_keys: templates.map((template) => template.template_key),
  asset_ids: assets.map((asset) => asset.instance_id),
  config,
});
