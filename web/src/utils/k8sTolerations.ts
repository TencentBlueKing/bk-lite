export const MAX_K8S_DS_TOLERATIONS = 16;
export const K8S_DS_TOLERATION_EFFECTS = ['NoSchedule', 'NoExecute'] as const;

export const DEFAULT_K8S_DS_TOLERATIONS: K8sToleration[] = [
  { key: 'node-role.kubernetes.io/control-plane', effect: 'NoSchedule' },
  { key: 'node-role.kubernetes.io/master', effect: 'NoSchedule' }
];

export type K8sTolerationEffect = (typeof K8S_DS_TOLERATION_EFFECTS)[number];

export interface K8sToleration {
  key: string;
  effect: K8sTolerationEffect;
  value?: string;
}

export type K8sTolerationMode = 'default' | 'custom' | 'none';

const NAME_RE = /^[A-Za-z0-9]([A-Za-z0-9._-]{0,61}[A-Za-z0-9])?$/;
const DNS_LABEL_RE = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;
const ALLOWED_FIELDS = new Set(['key', 'effect', 'value']);

const isValidKey = (key: unknown): key is string => {
  if (typeof key !== 'string' || !key || key.includes('__') || (key.match(/\//g) || []).length > 1) {
    return false;
  }
  if (key.includes('/')) {
    const [prefix, name] = key.split('/');
    if (
      prefix.length > 253 ||
      !prefix.split('.').every((part) => DNS_LABEL_RE.test(part)) ||
      !NAME_RE.test(name)
    ) {
      return false;
    }
    return true;
  }
  return NAME_RE.test(key);
};

const isValidValue = (value: unknown): value is string => {
  if (typeof value !== 'string' || value.includes('__')) {
    return false;
  }
  return !value || NAME_RE.test(value);
};

const isValidItem = (entry: unknown): entry is K8sToleration => {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
    return false;
  }
  const item = entry as Record<string, unknown>;
  if (Object.keys(item).some((field) => !ALLOWED_FIELDS.has(field))) {
    return false;
  }
  if (!isValidKey(item.key)) {
    return false;
  }
  if (item.effect !== 'NoSchedule' && item.effect !== 'NoExecute') {
    return false;
  }
  if (item.value !== undefined && item.value !== null && !isValidValue(item.value)) {
    return false;
  }
  return true;
};

export const isValidK8sTolerations = (value: unknown): boolean => {
  if (value == null) {
    return true;
  }
  if (!Array.isArray(value) || value.length > MAX_K8S_DS_TOLERATIONS) {
    return false;
  }
  return value.every(isValidItem);
};

export const normalizeK8sTolerations = (
  value: unknown
): K8sToleration[] | null => {
  if (value == null) {
    return null;
  }
  if (!isValidK8sTolerations(value) || !Array.isArray(value)) {
    throw new Error('invalid k8s tolerations');
  }
  return (value as K8sToleration[]).map((entry) => {
    const item: K8sToleration = {
      key: entry.key,
      effect: entry.effect
    };
    if (typeof entry.value === 'string' && entry.value !== '') {
      item.value = entry.value;
    }
    return item;
  });
};

export const k8sTolerationModeFromValue = (
  value: unknown
): K8sTolerationMode => {
  if (Array.isArray(value) && value.length === 0) {
    return 'none';
  }
  if (Array.isArray(value)) {
    return 'custom';
  }
  return 'default';
};

export const k8sTolerationsFromMode = (
  mode: K8sTolerationMode,
  items?: unknown
): K8sToleration[] | null => {
  if (mode === 'none') {
    return [];
  }
  if (mode === 'custom') {
    return normalizeK8sTolerations(items ?? []);
  }
  return null;
};
