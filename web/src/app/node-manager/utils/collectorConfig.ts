export interface CollectorConfigRef {
  collector_id?: string;
  configuration_id?: string | number | Array<string | number> | null;
}

export interface MainConfigCandidate {
  key?: string;
  id?: string;
  collector_id?: string;
}

export function normalizeConfigurationIds(
  configurationId: CollectorConfigRef['configuration_id']
): string[] {
  if (configurationId == null || configurationId === '') {
    return [];
  }
  if (Array.isArray(configurationId)) {
    return configurationId.map(String).filter(Boolean);
  }
  return [String(configurationId)];
}

export function resolveMainConfig<T extends MainConfigCandidate>(
  configs: T[],
  collector: CollectorConfigRef
): T | null {
  const configurationIds = normalizeConfigurationIds(collector.configuration_id);
  if (configurationIds.length) {
    const matchedById = configs.find(
      (config) =>
        configurationIds.includes(String(config.key ?? '')) ||
        configurationIds.includes(String(config.id ?? ''))
    );
    if (matchedById) {
      return matchedById;
    }
  }
  if (!collector.collector_id) {
    return null;
  }
  return (
    configs.find((config) => config.collector_id === collector.collector_id) ||
    null
  );
}

export function buildConfigModalFormData<T extends Record<string, unknown>>(
  form: T
): T & { configInfo: string } {
  return {
    ...form,
    configInfo: String(form.content || form.configInfo || '')
  };
}

export function asCollectorStatusList(
  collectors: unknown
): Array<Record<string, any>> {
  return Array.isArray(collectors) ? collectors : [];
}

export function applyConfigFormValues(
  formInstance: {
    resetFields: () => void;
    setFieldsValue: (values: Record<string, unknown>) => void;
  } | null,
  type: string,
  values: Record<string, unknown>
): boolean {
  if (!formInstance) {
    return false;
  }
  formInstance.resetFields();
  if (['edit', 'edit_child'].includes(type)) {
    formInstance.setFieldsValue(values);
  }
  return true;
}
