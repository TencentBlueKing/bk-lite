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

export const EXECUTOR_TYPE_TAG = 'executor';

const EXECUTOR_COLLECTOR_ID_PREFIXES = ['natsexecutor_', 'ansibleexecutor_'];
const EXECUTOR_COLLECTOR_NAMES = ['NATS-Executor', 'Ansible-Executor'];

export function asCollectorStatusList(
  collectors: unknown
): Array<Record<string, any>> {
  return Array.isArray(collectors) ? collectors : [];
}

export function isExecutorCollector(collector: {
  collector_id?: unknown;
  id?: unknown;
  name?: unknown;
  collector_name?: unknown;
}): boolean {
  const id = String(collector.collector_id || collector.id || '');
  if (EXECUTOR_COLLECTOR_ID_PREFIXES.some((prefix) => id.startsWith(prefix))) {
    return true;
  }
  const name = String(collector.name || collector.collector_name || '');
  return EXECUTOR_COLLECTOR_NAMES.includes(name);
}

export function mergeNodeCollectorStatuses(
  collectors: unknown,
  collectorsInstall: unknown
): Array<Record<string, any>> {
  const running = asCollectorStatusList(collectors);
  const installed = asCollectorStatusList(collectorsInstall);
  const collectorIds = new Set(running.map((item) => item.collector_id));
  return [
    ...running,
    ...installed.filter((item) => !collectorIds.has(item.collector_id))
  ];
}

export function listNodeHostedCollectors(record?: {
  status?: { collectors?: unknown; collectors_install?: unknown };
  [key: string]: any;
} | null): Array<Record<string, any>> {
  return mergeNodeCollectorStatuses(
    record?.status?.collectors,
    record?.status?.collectors_install
  );
}

export function filterCollectorsForOperationType<
  T extends {
    collector_id?: unknown;
    id?: unknown;
    name?: unknown;
    collector_name?: unknown;
    tags?: unknown;
  }
>(collectors: T[], typeTag: string): T[] {
  if (typeTag === EXECUTOR_TYPE_TAG) {
    return collectors.filter(
      (item) =>
        isExecutorCollector(item) ||
        (Array.isArray(item.tags) && item.tags.includes(EXECUTOR_TYPE_TAG))
    );
  }
  return collectors.filter(
    (item) => Array.isArray(item.tags) && item.tags.includes(typeTag)
  );
}

export interface CollectorOperationSelectGroup {
  label: string;
  title: string;
  options: Array<{ label: string; value: string }>;
}

export function groupCollectorsForOperationSelect(
  collectors: Array<{ id: string; name: string }>,
  getLabelKey: (name: string) => string | undefined
): CollectorOperationSelectGroup[] {
  const options: CollectorOperationSelectGroup[] = [];
  collectors.forEach((item) => {
    const tag =
      getLabelKey(item.name) ||
      (isExecutorCollector(item) ? 'Executor' : item.name);
    const option = { label: item.name, value: item.id };
    const tagIndex = options.findIndex((group) => group.title === tag);
    if (tagIndex >= 0) {
      options[tagIndex].options.push(option);
      return;
    }
    options.push({
      label: tag,
      title: tag,
      options: [option]
    });
  });
  return options;
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
