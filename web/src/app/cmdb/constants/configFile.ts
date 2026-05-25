export const CONFIG_FILE_SUPPORTED_MODEL_IDS = ['host'];

export const isConfigFileSupportedModel = (modelId?: string | null) => (
  !!modelId && CONFIG_FILE_SUPPORTED_MODEL_IDS.includes(modelId)
);
