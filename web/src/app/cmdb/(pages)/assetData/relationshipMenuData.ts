const getAssociationId = (item: unknown): unknown => {
  if (!item || typeof item !== 'object') return undefined;
  return (item as { model_asst_id?: unknown }).model_asst_id;
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
