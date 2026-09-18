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

export function asCollectorCatalogList<T = Record<string, any>>(
  data: unknown
): T[] {
  if (Array.isArray(data)) {
    return data as T[];
  }
  if (!data || typeof data !== 'object') {
    return [];
  }
  const record = data as { items?: unknown; results?: unknown };
  if (Array.isArray(record.items)) {
    return record.items as T[];
  }
  if (Array.isArray(record.results)) {
    return record.results as T[];
  }
  return [];
}

export function collectorDisplayName(collector?: {
  name?: unknown;
  collector_name?: unknown;
  collector?: unknown;
} | null): string {
  return String(
    collector?.collector_name || collector?.name || collector?.collector || ''
  ).trim();
}

export function parseCollectorQueryNames(value?: string | null): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const part of String(value || '').split(',')) {
    const name = part.trim();
    if (!name) continue;
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    names.push(name);
  }
  return names;
}

export function isSameCollectorName(
  collector: {
    name?: unknown;
    collector_name?: unknown;
    collector?: unknown;
  },
  names: string | string[]
): boolean {
  const current = collectorDisplayName(collector).toLowerCase();
  if (!current) return false;
  const targets = Array.isArray(names) ? names : parseCollectorQueryNames(names);
  return targets.some((name) => name.toLowerCase() === current);
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

export function listNodeUpgradeableCollectors(record?: {
  versions?: Array<{
    component_type?: unknown;
    component_id?: unknown;
    latest_version?: unknown;
    upgradeable?: unknown;
  }>;
  status?: { collectors?: unknown; collectors_install?: unknown };
  [key: string]: any;
} | null): Array<{ componentId: string; name: string; latestVersion: string }> {
  const hosted = listNodeHostedCollectors(record);
  const seen = new Set<string>();
  const result: Array<{
    componentId: string;
    name: string;
    latestVersion: string;
  }> = [];
  for (const version of record?.versions || []) {
    if (String(version.component_type || '') !== 'collector') continue;
    if (!version.upgradeable) continue;
    const componentId = String(version.component_id || '').trim();
    if (!componentId || seen.has(componentId)) continue;
    seen.add(componentId);
    const matched = findHostedCollector(hosted, componentId);
    const latestVersion = asPackageVersion(version.latest_version);
    result.push({
      componentId,
      name: collectorDisplayName(matched) || componentId,
      latestVersion: latestVersion || '--'
    });
  }
  return result;
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
  options: Array<{
    label: string;
    value: string;
    disabled?: boolean;
    title?: string;
    updateTag?: string;
  }>;
}

export function groupCollectorsForOperationSelect(
  collectors: Array<{
    id?: string | number;
    name?: string;
    latest_package_version?: string;
  }>,
  getLabelKey: (name: string) => string | undefined,
  selectOptions?: { requirePackage?: boolean; missingPackageHint?: string }
): CollectorOperationSelectGroup[] {
  const groups: CollectorOperationSelectGroup[] = [];
  collectors.forEach((item) => {
    const name = String(item.name || '');
    const tag =
      getLabelKey(name) ||
      (isExecutorCollector(item) ? 'Executor' : name);
    const option: {
      label: string;
      value: string;
      disabled?: boolean;
      title?: string;
    } = {
      label: name,
      value: String(item.id ?? '')
    };
    if (selectOptions?.requirePackage) {
      const missingPackage = !item.latest_package_version;
      option.disabled = missingPackage;
      option.title = missingPackage ? selectOptions.missingPackageHint : undefined;
    }
    const tagIndex = groups.findIndex((group) => group.title === tag);
    if (tagIndex >= 0) {
      groups[tagIndex].options.push(option);
      return;
    }
    groups.push({
      label: tag,
      title: tag,
      options: [option]
    });
  });
  return groups;
}

export interface CollectorUpdateHint {
  name: string;
  collectorId?: string;
  currentVersion?: string;
  latestVersion?: string;
}

const hintKey = (value: string) => value.trim().toLowerCase();

const GENERIC_COLLECTOR_ID_TOKENS = new Set([
  'exporter',
  'linux',
  'windows',
  'arm64',
  'amd64',
  'x86',
  'x64',
  'x86_64'
]);

function asPackageVersion(value: unknown): string {
  const version = String(value ?? '').trim();
  if (!version) return '';
  const normalized = version.toLowerCase();
  if (normalized === 'unknown' || normalized === '--') return '';
  return version;
}

function collectorIdCore(value: string): string {
  return value
    .split(/[_-]+/)
    .filter((token) => token && !GENERIC_COLLECTOR_ID_TOKENS.has(token))
    .join('_');
}

export function collectorIdsMatch(left?: string, right?: string): boolean {
  const a = String(left || '').trim().toLowerCase();
  const b = String(right || '').trim().toLowerCase();
  if (!a || !b) return false;
  if (a === b) return true;
  if (
    a.startsWith(`${b}_`) ||
    b.startsWith(`${a}_`) ||
    a.startsWith(`${b}-`) ||
    b.startsWith(`${a}-`)
  ) {
    return true;
  }
  const coreA = collectorIdCore(a);
  const coreB = collectorIdCore(b);
  return Boolean(coreA && coreB && coreA === coreB);
}

function findHostedCollector(
  hosted: Array<Record<string, any>>,
  componentId?: string
): Record<string, any> | undefined {
  return hosted.find((item) =>
    collectorIdsMatch(componentId, String(item.collector_id || ''))
  );
}

function findCatalogCollector<
  T extends { id?: string; name?: string; latest_package_version?: string }
>(
  collectors: T[],
  hint: { collectorId?: string; name?: string }
): T | undefined {
  const nameKey = hintKey(String(hint.name || ''));
  return collectors.find((collector) => {
    if (collectorIdsMatch(hint.collectorId, String(collector.id || ''))) {
      return true;
    }
    if (!nameKey) return false;
    return hintKey(String(collector.name || '')) === nameKey;
  });
}

export function matchCollectorUpdateHint(
  option: { label?: string; value?: string },
  hints: CollectorUpdateHint[]
): CollectorUpdateHint | undefined {
  return hints.find(
    (hint) =>
      collectorIdsMatch(hint.collectorId, option.value) ||
      collectorIdsMatch(hint.name, option.value) ||
      hintKey(hint.name) === hintKey(String(option.label || ''))
  );
}

export function listCollectorUpdateHints(
  nodes: Array<{
    versions?: Array<{
      component_type?: unknown;
      component_id?: unknown;
      version?: unknown;
      latest_version?: unknown;
      upgradeable?: unknown;
    }>;
    status?: { collectors?: unknown; collectors_install?: unknown };
    [key: string]: any;
  }> = [],
  importedNames: string[] = []
): CollectorUpdateHint[] {
  const byName = new Map<string, CollectorUpdateHint>();
  const add = (hint: CollectorUpdateHint) => {
    const key = hintKey(hint.name);
    if (!key) return;
    const prev = byName.get(key);
    byName.set(key, {
      name: prev?.name || hint.name,
      collectorId: prev?.collectorId || hint.collectorId,
      currentVersion: prev?.currentVersion || hint.currentVersion,
      latestVersion: prev?.latestVersion || hint.latestVersion
    });
  };
  importedNames.forEach((name) => add({ name }));
  (nodes || []).forEach((node) => {
    listNodeUpgradeableCollectors(node).forEach((item) => {
      add({
        name: item.name,
        collectorId: item.componentId,
        latestVersion: item.latestVersion
      });
    });
    const hosted = listNodeHostedCollectors(node);
    (node.versions || []).forEach((version) => {
      if (String(version.component_type || '') !== 'collector') return;
      const componentId = String(version.component_id || '').trim();
      const matched = findHostedCollector(hosted, componentId);
      const name = collectorDisplayName(matched);
      if (!name) return;
      const imported = importedNames.some(
        (item) => hintKey(item) === hintKey(name)
      );
      if (!imported && !version.upgradeable) return;
      add({
        name,
        collectorId: componentId,
        currentVersion: asPackageVersion(version.version) || undefined,
        latestVersion: version.upgradeable
          ? asPackageVersion(version.latest_version) || undefined
          : undefined
      });
    });
  });
  return [...byName.values()];
}

export function formatCollectorUpdateTag(
  hint: CollectorUpdateHint | undefined,
  labels: { updatable: (version: string) => string; imported: string }
): string | undefined {
  const latestVersion = asPackageVersion(hint?.latestVersion);
  if (latestVersion) {
    return labels.updatable(latestVersion);
  }
  if (hint) {
    return labels.imported;
  }
  return undefined;
}

export function enrichCollectorUpdateHints(
  hints: CollectorUpdateHint[],
  collectors: Array<{
    id?: string;
    name?: string;
    latest_package_version?: string;
  }> = []
): CollectorUpdateHint[] {
  return (hints || []).map((hint) => {
    const item = findCatalogCollector(collectors, hint);
    return {
      ...hint,
      collectorId:
        (item?.id != null ? String(item.id) : undefined) || hint.collectorId,
      latestVersion:
        asPackageVersion(hint.latestVersion) ||
        asPackageVersion(item?.latest_package_version) ||
        undefined
    };
  });
}

export function mergeCatalogCollectorUpdateHints(
  hints: CollectorUpdateHint[],
  collectors: Array<{
    id?: string;
    name?: string;
    latest_package_version?: string;
  }> = [],
  nodes: Array<{
    versions?: Array<{
      component_type?: unknown;
      component_id?: unknown;
      version?: unknown;
      latest_version?: unknown;
      upgradeable?: unknown;
    }>;
    status?: { collectors?: unknown; collectors_install?: unknown };
    [key: string]: any;
  }> = []
): CollectorUpdateHint[] {
  const byName = new Map<string, CollectorUpdateHint>();
  const add = (hint: CollectorUpdateHint) => {
    const key = hintKey(hint.name);
    if (!key) return;
    const prev = byName.get(key);
    byName.set(key, {
      name: prev?.name || hint.name,
      collectorId: prev?.collectorId || hint.collectorId,
      currentVersion: prev?.currentVersion || hint.currentVersion,
      latestVersion: prev?.latestVersion || hint.latestVersion
    });
  };
  enrichCollectorUpdateHints(hints, collectors).forEach(add);
  (nodes || []).forEach((node) => {
    const hosted = listNodeHostedCollectors(node);
    const versions = (node.versions || []).filter(
      (version) => String(version.component_type || '') === 'collector'
    );
    const seen = new Set<string>();
    const addCatalogHint = (
      hostedItem?: Record<string, any>,
      version?: {
        component_id?: unknown;
        version?: unknown;
        latest_version?: unknown;
      }
    ) => {
      const componentId = String(
        version?.component_id || hostedItem?.collector_id || ''
      ).trim();
      const catalog = findCatalogCollector(collectors, {
        collectorId: componentId,
        name: collectorDisplayName(hostedItem)
      });
      const name =
        collectorDisplayName(hostedItem) || String(catalog?.name || '');
      if (!name) return;
      const key = hintKey(name);
      if (seen.has(key)) return;
      const currentVersion = asPackageVersion(version?.version);
      const latestVersion = asPackageVersion(
        catalog?.latest_package_version || version?.latest_version
      );
      if (!latestVersion) return;
      if (currentVersion && currentVersion === latestVersion) return;
      seen.add(key);
      add({
        name,
        collectorId:
          catalog?.id != null ? String(catalog.id) : componentId || undefined,
        currentVersion: currentVersion || undefined,
        latestVersion
      });
    };
    hosted.forEach((item) => {
      const version = versions.find((row) =>
        collectorIdsMatch(
          String(row.component_id || ''),
          String(item.collector_id || '')
        )
      );
      addCatalogHint(item, version);
    });
    versions.forEach((version) => {
      addCatalogHint(
        findHostedCollector(hosted, String(version.component_id || '')),
        version
      );
    });
  });
  return [...byName.values()];
}

export function promotePendingCollectorOptions(
  groups: CollectorOperationSelectGroup[],
  hints: CollectorUpdateHint[],
  pendingGroupLabel: string,
  labels: { updatable: (version: string) => string; imported: string }
): CollectorOperationSelectGroup[] {
  if (!hints.length) return groups;
  const matchHint = (option: { label: string; value: string }) =>
    matchCollectorUpdateHint(option, hints);
  const pendingOptions: CollectorOperationSelectGroup['options'] = [];
  const seen = new Set<string>();
  const rest = groups
    .map((group) => ({
      ...group,
      options: group.options.filter((option) => {
        const hint = matchHint(option);
        if (!hint) return true;
        if (!seen.has(option.value)) {
          seen.add(option.value);
          pendingOptions.push({
            ...option,
            updateTag: formatCollectorUpdateTag(hint, labels)
          });
        }
        return false;
      })
    }))
    .filter((group) => group.options.length);
  if (!pendingOptions.length) return groups;
  return [
    {
      label: pendingGroupLabel,
      title: pendingGroupLabel,
      options: pendingOptions
    },
    ...rest
  ];
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

export interface CollectorPackStatusTag {
  name: string;
  color: string;
  tooltip: string;
}

type Translate = (
  key: string,
  fallback?: string,
  values?: Record<string, string | number>
) => string;

export function buildCollectorPackStatusTag(
  version: string | null | undefined,
  t: Translate,
  options?: { pinnedVersion?: string | null }
): CollectorPackStatusTag {
  const packVersion = String(version || '').trim();
  const pinnedVersion = String(options?.pinnedVersion || '').trim();
  if (packVersion) {
    return {
      name: packVersion,
      color: 'blue',
      tooltip: pinnedVersion
        ? t('node-manager.packetManage.pinnedPackHint', '', {
          version: pinnedVersion
        })
        : t('node-manager.packetManage.importedPackHint', '', {
          version: packVersion
        })
    };
  }
  return {
    name: t('node-manager.packetManage.missingPack'),
    color: 'warning',
    tooltip: t('node-manager.packetManage.missingPackHint')
  };
}
