export const K8S_TOLERATION_EFFECTS = ['NoSchedule', 'NoExecute'] as const;

export type K8sTolerationEffect = (typeof K8S_TOLERATION_EFFECTS)[number];

export interface K8sDaemonSetToleration {
  key: string;
  effect: K8sTolerationEffect;
  value?: string;
}

export const DEFAULT_K8S_DAEMONSET_TOLERATIONS: K8sDaemonSetToleration[] = [
  { key: 'node-role.kubernetes.io/control-plane', effect: 'NoSchedule' },
  { key: 'node-role.kubernetes.io/master', effect: 'NoSchedule' },
];

export const MAX_K8S_DAEMONSET_TOLERATIONS = 16;
const PLACEHOLDER_TOKEN = '__';
const NAME_RE = /^[A-Za-z0-9]([A-Za-z0-9._-]{0,61}[A-Za-z0-9])?$/;
const DNS_LABEL_RE = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;

export const isUnsetTolerations = (
  value: K8sDaemonSetToleration[] | null | undefined
): value is null | undefined => value == null;

const validateKey = (key: unknown): string | null => {
  if (typeof key !== 'string' || !key) {
    return 'keyRequired';
  }
  if (key.includes(PLACEHOLDER_TOKEN)) {
    return 'placeholderReserved';
  }
  if ((key.match(/\//g) || []).length > 1) {
    return 'keyInvalid';
  }
  let name = key;
  if (key.includes('/')) {
    const [prefix, rest] = key.split('/');
    name = rest;
    if (
      prefix.length > 253 ||
      !prefix.split('.').every((part) => DNS_LABEL_RE.test(part))
    ) {
      return 'keyInvalid';
    }
  }
  if (!NAME_RE.test(name)) {
    return 'keyInvalid';
  }
  return null;
};

const validateValue = (value: unknown): string | null => {
  if (value == null) return null;
  if (typeof value !== 'string') return 'valueInvalid';
  if (value.includes(PLACEHOLDER_TOKEN)) return 'placeholderReserved';
  if (value && !NAME_RE.test(value)) return 'valueInvalid';
  return null;
};

export const normalizeEditorToleration = (
  item: Partial<K8sDaemonSetToleration> | undefined
): K8sDaemonSetToleration => {
  const normalized: K8sDaemonSetToleration = {
    key: String(item?.key ?? '').trim(),
    effect:
      item?.effect === 'NoExecute' || item?.effect === 'NoSchedule'
        ? item.effect
        : 'NoSchedule',
  };
  if (item && 'value' in item && item.value != null && item.value !== '') {
    normalized.value = String(item.value);
  }
  return normalized;
};

export const validateK8sDaemonSetTolerations = (
  value: K8sDaemonSetToleration[] | null | undefined
): string | null => {
  if (isUnsetTolerations(value)) {
    return null;
  }
  if (!Array.isArray(value)) {
    return 'mustBeArray';
  }
  if (value.length > MAX_K8S_DAEMONSET_TOLERATIONS) {
    return 'tooMany';
  }
  for (const item of value) {
    if (!item || typeof item !== 'object') {
      return 'itemInvalid';
    }
    const extra = Object.keys(item).filter(
      (field) => field !== 'key' && field !== 'effect' && field !== 'value'
    );
    if (extra.length) {
      return 'unknownFields';
    }
    const keyError = validateKey(item.key);
    if (keyError) return keyError;
    if (item.effect !== 'NoSchedule' && item.effect !== 'NoExecute') {
      return 'effectInvalid';
    }
    const valueError = validateValue(item.value);
    if (valueError) return valueError;
  }
  return null;
};

export const toRequestTolerations = (
  value: K8sDaemonSetToleration[] | null | undefined
): K8sDaemonSetToleration[] | null => {
  if (isUnsetTolerations(value)) {
    return null;
  }
  return value.map((item) => normalizeEditorToleration(item));
};
