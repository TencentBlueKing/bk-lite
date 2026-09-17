const getAssociationId = (item: unknown): unknown => {
  if (!item || typeof item !== 'object') return undefined;
  return (item as { model_asst_id?: unknown }).model_asst_id;
};

const getAssociationInstanceCount = (item: unknown): number => {
  if (!item || typeof item !== 'object') return 0;
  const instances = (item as { inst_list?: unknown }).inst_list;
  return Array.isArray(instances) ? instances.length : 0;
};

export function visibleRelationshipAssociations<T>(
  associations: readonly T[]
): T[] {
  return associations.filter((item) => getAssociationInstanceCount(item) > 0);
}

export interface RelationshipMenuItem {
  text: string;
  value: number;
  model_asst_id: string;
}

export interface RelationshipMenuSection {
  title: string;
  children: RelationshipMenuItem[];
}

interface AssociationTypeLike {
  asst_id?: string;
  asst_name?: string;
}

interface AssociationRecord {
  model_asst_id?: unknown;
  asst_id?: unknown;
  src_model_id?: unknown;
  dst_model_id?: unknown;
  src_model_name?: unknown;
  dst_model_name?: unknown;
}

export function buildRelationshipMenuSections({
  instances,
  assoTypes,
  modelId,
}: {
  instances: readonly unknown[];
  assoTypes: readonly AssociationTypeLike[];
  modelId: string;
}): RelationshipMenuSection[] {
  const grouped = new Map<string, RelationshipMenuItem[]>();

  visibleRelationshipAssociations(instances).forEach((item) => {
    if (!item || typeof item !== 'object') return;
    const record = item as AssociationRecord;
    const associationId = getAssociationId(item);
    if (typeof associationId !== 'string' || !associationId) return;

    const asstId = typeof record.asst_id === 'string' ? record.asst_id : '';
    const title =
      assoTypes.find((type) => type.asst_id === asstId)?.asst_name || '--';
    const text =
      record.dst_model_id === modelId
        ? String(record.src_model_name || record.src_model_id || '')
        : String(record.dst_model_name || record.dst_model_id || '');
    const child: RelationshipMenuItem = {
      model_asst_id: associationId,
      text,
      value: getAssociationInstanceCount(item),
    };

    const existing = grouped.get(title) || [];
    const previous = existing.find((entry) => entry.model_asst_id === associationId);
    if (!previous) {
      existing.push(child);
    } else if (child.value > previous.value) {
      Object.assign(previous, child);
    }
    grouped.set(title, existing);
  });

  return Array.from(grouped.entries())
    .map(([title, children]) => ({ title, children }))
    .filter((section) => section.children.length > 0);
}

export const getDefaultExpandedRelationshipKeys = (
  associations: readonly unknown[]
): string[] => associations.flatMap((item) => {
  const associationId = getAssociationId(item);
  return typeof associationId === 'string' && getAssociationInstanceCount(item) > 0
    ? [associationId]
    : [];
});

export const areAllRelationshipsExpanded = (
  activeKeys: readonly string[],
  allKeys: readonly string[]
): boolean => {
  if (!allKeys.length) return false;
  const activeKeySet = new Set(activeKeys);
  return allKeys.every((key) => activeKeySet.has(key));
};
