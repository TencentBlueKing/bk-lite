import {
  buildBulkApplyPayload,
  buildCollectionPolicyBulkConfig,
  formatTemplateListName,
  getPrimaryNoticeType,
  getTemplateKey,
  type BulkConfig,
  type PolicyTemplateItem
} from '@/app/monitor/(pages)/event/template/templateBulkUtils';

export const COLLECTION_POLICY_FIELD = 'monitor_policy_template_keys';
export const COLLECTION_POLICY_NAME_PREFIX_FIELD = 'monitor_policy_name_prefix';
export const COLLECTION_POLICY_ALERT_CENTER_FIELD =
  'monitor_policy_push_alert_center';
export const COLLECTION_POLICY_CONTROL_WIDTH = 300;
export const ALERT_CENTER_NATS_METHOD = 'receive_alert_events';

const COLLECTION_POLICY_UI_FIELDS = [
  COLLECTION_POLICY_FIELD,
  COLLECTION_POLICY_NAME_PREFIX_FIELD,
  COLLECTION_POLICY_ALERT_CENTER_FIELD
] as const;

export const samePluginId = (
  left: string | number | null | undefined,
  right: string | number | null | undefined
): boolean => {
  if (left === undefined || left === null || left === '') return false;
  if (right === undefined || right === null || right === '') return false;
  return String(left) === String(right);
};

export const isCustomPolicyTemplate = (item: PolicyTemplateItem): boolean =>
  item.template_type === 'custom';

export const filterTemplatesByPlugin = (
  templates: PolicyTemplateItem[],
  pluginId: string | number | null | undefined
): PolicyTemplateItem[] =>
  templates.filter(
    (item) =>
      Boolean(item.template_key) && samePluginId(item.plugin_id, pluginId)
  );

export const defaultSelectedTemplateKeys = (
  templates: PolicyTemplateItem[]
): string[] =>
  templates
    .filter((item) => !isCustomPolicyTemplate(item))
    .map((item) => getTemplateKey(item))
    .filter(Boolean);

export const COLLECTION_POLICY_HABIT_KEY_PREFIX =
  'integration.collectionPolicy.';

export const collectionPolicyHabitKey = (
  pluginId: string | number | null | undefined
): string | null => {
  if (pluginId === undefined || pluginId === null || pluginId === '') {
    return null;
  }
  return `${COLLECTION_POLICY_HABIT_KEY_PREFIX}${pluginId}`;
};

export const parseRememberedTemplateKeys = (
  habit: unknown
): string[] | null => {
  if (!habit || typeof habit !== 'object' || Array.isArray(habit)) {
    return null;
  }
  const keys = (habit as { template_keys?: unknown }).template_keys;
  if (!Array.isArray(keys)) return null;
  return keys
    .map((item) => String(item ?? '').trim())
    .filter(Boolean);
};

export const resolveRememberedTemplateKeys = (
  templates: PolicyTemplateItem[],
  remembered: string[] | null
): string[] => {
  if (remembered === null) return defaultSelectedTemplateKeys(templates);
  const available = new Set(
    templates.map((item) => getTemplateKey(item)).filter(Boolean)
  );
  const kept = remembered.filter((key) => available.has(key));
  if (kept.length || remembered.length === 0) return kept;
  return defaultSelectedTemplateKeys(templates);
};

export const parseRememberedPushAlertCenter = (
  habit: unknown
): boolean | null => {
  if (!habit || typeof habit !== 'object' || Array.isArray(habit)) {
    return null;
  }
  const value = (habit as { push_alert_center?: unknown }).push_alert_center;
  return typeof value === 'boolean' ? value : null;
};

export const collectionPolicyHabitValue = (
  selectedKeys: unknown,
  pushAlertCenter: unknown = false
): { template_keys: string[]; push_alert_center: boolean } => ({
  template_keys: Array.isArray(selectedKeys)
    ? selectedKeys.map((item) => String(item ?? '').trim()).filter(Boolean)
    : [],
  push_alert_center: Boolean(pushAlertCenter)
});

export const shouldSkipPolicyCreate = (selectedKeys: unknown): boolean =>
  !Array.isArray(selectedKeys) || selectedKeys.length === 0;

export const isCollectionPolicyUiField = (key: string): boolean =>
  COLLECTION_POLICY_UI_FIELDS.includes(
    key as (typeof COLLECTION_POLICY_UI_FIELDS)[number]
  );

export const omitCollectionPolicyField = <T extends object>(
  values: T
): Omit<
  T,
  | typeof COLLECTION_POLICY_FIELD
  | typeof COLLECTION_POLICY_NAME_PREFIX_FIELD
  | typeof COLLECTION_POLICY_ALERT_CENTER_FIELD
> => {
  const next = { ...values } as T & Record<string, unknown>;
  delete next[COLLECTION_POLICY_FIELD];
  delete next[COLLECTION_POLICY_NAME_PREFIX_FIELD];
  delete next[COLLECTION_POLICY_ALERT_CENTER_FIELD];
  return next;
};

export const resolvePolicyTemplateList = (
  data: unknown,
  pluginId: string | number | null | undefined
): PolicyTemplateItem[] => {
  const list = Array.isArray(data) ? data : [];
  return filterTemplatesByPlugin(list as PolicyTemplateItem[], pluginId);
};

export const selectedPolicyTemplates = (
  templates: PolicyTemplateItem[],
  selectedKeys: unknown
): PolicyTemplateItem[] => {
  if (!Array.isArray(selectedKeys) || !selectedKeys.length) return [];
  const keySet = new Set(selectedKeys.map(String));
  return templates.filter((item) => keySet.has(getTemplateKey(item)));
};

export const policyTemplateSelectOptions = (
  templates: PolicyTemplateItem[],
  groupLabels: { builtin: string; custom: string } = {
    builtin: '内置',
    custom: '自定义'
  }
): Array<{
  label: string;
  options: Array<{ label: string; value: string }>;
}> => {
  const builtin = templates.filter((item) => !isCustomPolicyTemplate(item));
  const custom = templates.filter(isCustomPolicyTemplate);
  const toOptions = (items: PolicyTemplateItem[]) =>
    items
      .map((item) => ({
        label: formatTemplateListName(item, templates),
        value: getTemplateKey(item)
      }))
      .filter((item) => item.value);
  const groups: Array<{
    label: string;
    options: Array<{ label: string; value: string }>;
  }> = [];
  if (builtin.length) {
    groups.push({ label: groupLabels.builtin, options: toOptions(builtin) });
  }
  if (custom.length) {
    groups.push({ label: groupLabels.custom, options: toOptions(custom) });
  }
  return groups;
};

export const pickAlertCenterChannelIds = (
  channels: Array<{ id?: string | number; channel_type?: string }>
): Array<string | number> =>
  channels
    .filter(
      (item) =>
        item.channel_type === 'nats' &&
        item.id !== undefined &&
        item.id !== null &&
        item.id !== ''
    )
    .map((item) => item.id as string | number);

export const mergeNoticeTypeIds = (
  current: Array<string | number> = [],
  extra: Array<string | number> = []
): Array<string | number> => {
  const merged: Array<string | number> = [];
  const seen = new Set<string>();
  for (const id of [...current, ...extra]) {
    if (id === undefined || id === null || id === '') continue;
    const key = String(id);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(id);
  }
  return merged;
};

export const excludeNoticeTypeIds = (
  current: Array<string | number> = [],
  remove: Array<string | number> = []
): Array<string | number> => {
  const removeSet = new Set(remove.map(String));
  return current.filter((id) => !removeSet.has(String(id)));
};

export const applyPushAlertCenterToNotice = ({
  pushAlertCenter,
  noticeTypeIds = [],
  noticeUsers = [],
  alertCenterChannelIds = [],
  channels = []
}: {
  pushAlertCenter: boolean;
  noticeTypeIds?: Array<string | number>;
  noticeUsers?: string[];
  alertCenterChannelIds?: Array<string | number>;
  channels?: Array<{ id: string | number; channel_type?: string }>;
}): Partial<BulkConfig> => {
  const nextIds = pushAlertCenter
    ? mergeNoticeTypeIds(noticeTypeIds, alertCenterChannelIds)
    : excludeNoticeTypeIds(noticeTypeIds, alertCenterChannelIds);
  const selectedTypes = channels
    .filter((item) => nextIds.some((id) => String(id) === String(item.id)))
    .map((item) => item.channel_type);
  const onlyNats =
    selectedTypes.length > 0 && selectedTypes.every((type) => type === 'nats');
  return {
    ...(pushAlertCenter ? { notice: true } : {}),
    notice_type_ids: nextIds,
    notice_type: getPrimaryNoticeType(nextIds, channels),
    notice_users: onlyNats ? [] : noticeUsers
  };
};

export const buildCollectionPolicyNoticeOverrides = (
  pushAlertCenter: boolean,
  channelIds: Array<string | number>
): Partial<BulkConfig> => {
  if (!pushAlertCenter || !channelIds.length) return {};
  return {
    notice: true,
    notice_type: 'nats',
    notice_type_ids: channelIds,
    notice_users: []
  };
};

export const extractCollectInstanceIds = (
  collectResult: unknown,
  collectParams: { instances?: Array<{ instance_id?: unknown }> } = {}
): string[] => {
  const fromResult =
    collectResult &&
    typeof collectResult === 'object' &&
    Array.isArray((collectResult as { instance_ids?: unknown }).instance_ids)
      ? (collectResult as { instance_ids: unknown[] }).instance_ids
      : [];
  if (fromResult.length) {
    return fromResult.map((item) => String(item ?? '').trim()).filter(Boolean);
  }
  return (collectParams.instances || [])
    .map((item) => String(item?.instance_id ?? '').trim())
    .filter(Boolean);
};

export const buildCollectionPolicyApplyPayload = ({
  monitorObjectId,
  templates,
  instanceIds,
  namePrefix,
  pushAlertCenter,
  alertCenterChannelIds
}: {
  monitorObjectId: string | number;
  templates: PolicyTemplateItem[];
  instanceIds: string[];
  namePrefix?: string;
  pushAlertCenter?: boolean;
  alertCenterChannelIds?: Array<string | number>;
}) => {
  if (!templates.length || !instanceIds.length) return null;
  const channelIds = alertCenterChannelIds || [];
  return buildBulkApplyPayload({
    monitorObjectId,
    templates,
    assets: instanceIds.map((instance_id) => ({ instance_id })),
    config: buildCollectionPolicyBulkConfig(
      {
        ...(namePrefix === undefined ? {} : { name_prefix: namePrefix }),
        ...buildCollectionPolicyNoticeOverrides(
          Boolean(pushAlertCenter),
          channelIds
        )
      },
      channelIds.map((id) => ({ id, channel_type: 'nats' }))
    )
  });
};
