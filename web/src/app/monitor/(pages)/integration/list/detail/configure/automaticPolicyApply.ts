import {
  buildBulkApplyPayload,
  buildCollectionPolicyBulkConfig,
  formatTemplateListName,
  getTemplateKey,
  type PolicyTemplateItem
} from '@/app/monitor/(pages)/event/template/templateBulkUtils';

export const COLLECTION_POLICY_FIELD = 'monitor_policy_template_keys';
export const COLLECTION_POLICY_CONTROL_WIDTH = 300;

export const samePluginId = (
  left: string | number | null | undefined,
  right: string | number | null | undefined
): boolean => {
  if (left === undefined || left === null || left === '') return false;
  if (right === undefined || right === null || right === '') return false;
  return String(left) === String(right);
};

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
  templates.map((item) => getTemplateKey(item)).filter(Boolean);

export const shouldSkipPolicyCreate = (selectedKeys: unknown): boolean =>
  !Array.isArray(selectedKeys) || selectedKeys.length === 0;

export const omitCollectionPolicyField = <T extends object>(
  values: T
): Omit<T, typeof COLLECTION_POLICY_FIELD> => {
  const next = { ...values } as T & Record<string, unknown>;
  delete next[COLLECTION_POLICY_FIELD];
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
  templates: PolicyTemplateItem[]
): Array<{ label: string; value: string }> =>
  templates.map((item) => ({
    label: formatTemplateListName(item, templates),
    value: getTemplateKey(item)
  }));

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
  instanceIds
}: {
  monitorObjectId: string | number;
  templates: PolicyTemplateItem[];
  instanceIds: string[];
}) => {
  if (!templates.length || !instanceIds.length) return null;
  return buildBulkApplyPayload({
    monitorObjectId,
    templates,
    assets: instanceIds.map((instance_id) => ({ instance_id })),
    config: buildCollectionPolicyBulkConfig()
  });
};
