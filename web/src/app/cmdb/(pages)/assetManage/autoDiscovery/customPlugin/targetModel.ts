export function isCustomPluginTargetModel(modelId: string) {
  return !String(modelId || '').startsWith('k8s_');
}

export function customPluginTargetOptions<T extends { value: string }>(models: T[], currentModelId = '') {
  return models.filter((item) => isCustomPluginTargetModel(item.value) || item.value === currentModelId);
}
