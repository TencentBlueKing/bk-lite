interface ModelAssociationLike {
  asst_id?: string;
  src_model_id?: string;
  dst_model_id?: string;
}

interface ModelLike {
  model_id?: string;
  model_name?: string;
}

export const getNetworkTopologyModelIds = (
  associations: ModelAssociationLike[],
): Set<string> => {
  const modelIds = (Array.isArray(associations) ? associations : [])
    .filter(
      (association) =>
        association.asst_id === 'belong' &&
        association.src_model_id === 'interface' &&
        association.dst_model_id,
    )
    .map((association) => String(association.dst_model_id));

  return new Set(modelIds);
};

export const filterNetworkTopologyModelOptions = (
  models: ModelLike[],
  supportedModelIds: Set<string>,
) =>
  (Array.isArray(models) ? models : [])
    .filter((model) => model.model_id && supportedModelIds.has(model.model_id))
    .map((model) => ({
      label: model.model_name || model.model_id || '',
      value: model.model_id || '',
    }));
