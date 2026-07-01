export type RecentChangeFilter = 'all' | 'mine' | 'highRisk';

export const HIGH_RISK_CHANGE_TYPES = ['delete_entity', 'delete_edge'] as const;

export type HighRiskChangeType = (typeof HIGH_RISK_CHANGE_TYPES)[number];

export const ASSET_CHANGE_SCENARIOS = [
  'device_lifecycle',
  'relation_change',
  'ordinary_attribute_change',
  'collect_automation_change',
] as const;

export interface ChangeRecordSummary {
  id?: string | number;
  created_at?: string;
  inst_id?: string | number;
  inst_name?: string;
  message?: string;
  model_id?: string;
  model_object?: string;
  operator?: string;
  type?: string;
}

export interface ClassificationLike {
  classification_id: string;
  classification_name: string;
}

export interface ModelLike {
  model_id: string;
  model_name: string;
  classification_id: string;
  icn?: string;
}

export interface CategoryEntryData {
  key: string;
  classification_id: string;
  title: string;
  count: number;
  target_model_id?: string;
  target_classification_id?: string;
  target_icn?: string;
}

export const buildRecentChangeQuery = (
  filter: RecentChangeFilter,
  operator?: string,
  type?: HighRiskChangeType,
  limit = 10,
  page = 1
) => {
  const query: Record<string, string | number> = {
    page,
    page_size: limit,
    scenarios: ASSET_CHANGE_SCENARIOS.join(','),
  };

  if (filter === 'mine' && operator) {
    query.operator = operator;
  }

  if (filter === 'highRisk' && type) {
    query.type = type;
  }

  return query;
};

export const isHighRiskChangeRecord = (record: { type?: string }) =>
  HIGH_RISK_CHANGE_TYPES.includes(record.type as HighRiskChangeType);

export const canLazyLoadRecentChanges = (filter: RecentChangeFilter) =>
  filter !== 'highRisk';

export const getRecentChangeTarget = (record: ChangeRecordSummary) =>
  String(
    record.model_object ||
    record.message ||
    record.inst_name ||
    record.inst_id ||
    '--'
  );

export const getRecentChangeMessage = (record: ChangeRecordSummary) =>
  String(record.message || '');

export const mergeRecentChangeRecords = <T extends { id?: string | number; created_at?: string; type?: string }>(
  records: T[],
  limit = 10
) => {
  const seen = new Set<string | number>();
  return records
    .filter(isHighRiskChangeRecord)
    .filter((record) => {
      const key = record.id ?? `${record.created_at}-${JSON.stringify(record)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => {
      const left = new Date(a.created_at || 0).getTime();
      const right = new Date(b.created_at || 0).getTime();
      return right - left;
    })
    .slice(0, limit);
};

export const buildCategoryEntries = ({
  groups,
  modelList,
  instanceCount,
  limit = 6,
}: {
  groups: ClassificationLike[];
  modelList: ModelLike[];
  instanceCount: Record<string, number>;
  limit?: number;
}): CategoryEntryData[] => {
  const groupOrder = new Map(groups.map((group, index) => [group.classification_id, index]));
  const visibleGroupIds = new Set(groups.map((group) => group.classification_id));
  const buckets = groups.map((group) => ({
    key: group.classification_id,
    classification_id: group.classification_id,
    title: group.classification_name,
    count: 0,
    models: [] as Array<ModelLike & { count: number }>,
  }));
  const bucketMap = new Map(buckets.map((bucket) => [bucket.classification_id, bucket]));

  modelList.forEach((model) => {
    if (!visibleGroupIds.has(model.classification_id)) return;
    const bucket = bucketMap.get(model.classification_id);
    if (!bucket) return;
    const count = instanceCount?.[model.model_id] || 0;
    bucket.count += count;
    bucket.models.push({ ...model, count });
  });

  return buckets
    .filter((bucket) => bucket.models.length > 0)
    .sort((left, right) => {
      if (right.count !== left.count) return right.count - left.count;
      return (groupOrder.get(left.classification_id) || 0) - (groupOrder.get(right.classification_id) || 0);
    })
    .slice(0, limit)
    .map((bucket) => {
      const targetModel = bucket.models.find((model) => model.count > 0) || bucket.models[0];
      return {
        key: bucket.key,
        classification_id: bucket.classification_id,
        title: bucket.title,
        count: bucket.count,
        target_model_id: targetModel?.model_id,
        target_classification_id: targetModel?.classification_id,
        target_icn: targetModel?.icn,
      };
    });
};
