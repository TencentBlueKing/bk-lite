const getAssociationId = (item: unknown): unknown => {
  if (!item || typeof item !== 'object') return undefined;
  return (item as { model_asst_id?: unknown }).model_asst_id;
};

const getAssociationInstanceCount = (item: unknown): number => {
  if (!item || typeof item !== 'object') return 0;
  const instances = (item as { inst_list?: unknown }).inst_list;
  return Array.isArray(instances) ? instances.length : 0;
};

export function mergeRelationshipAssociations<TInstance, TDefinition>(
  instances: readonly TInstance[],
  definitions: readonly TDefinition[]
): Array<TInstance | TDefinition> {
  const instanceAssociationIds = new Set(
    instances.map(getAssociationId)
  );

  return [
    ...instances,
    ...definitions.filter((item) => {
      const associationId = getAssociationId(item);
      return (
        associationId === undefined || !instanceAssociationIds.has(associationId)
      );
    }),
  ];
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
