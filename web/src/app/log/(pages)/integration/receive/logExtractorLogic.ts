import type { ExtractorType } from '@/app/log/types/extractor';

export const TYPE_SCOPED_COLLECT_TYPES = ['syslog', 'snmp_trap'] as const;
export const EXTRACTOR_CREATE_SAMPLE_STORAGE_KEY =
  'bk-lite.log-extractor.create-sample';

export type TypeScopedCollectType = (typeof TYPE_SCOPED_COLLECT_TYPES)[number];

export type ExtractorCreateTarget =
  | { kind: 'type'; collectType: TypeScopedCollectType }
  | { kind: 'instance'; instanceId: string }
  | { kind: 'unavailable'; reason: 'missing_instance' };

export type CollectTypeLinkFields = {
  id?: unknown;
  name: string;
  collector?: unknown;
  icon?: unknown;
  display_name?: unknown;
  description?: unknown;
  display_description?: unknown;
};

export const isTypeScopedCollectType = (
  value: unknown
): value is TypeScopedCollectType =>
  TYPE_SCOPED_COLLECT_TYPES.includes(value as TypeScopedCollectType);

export const resolveExtractorCreateTarget = (event: {
  collect_type?: unknown;
  instance_id?: unknown;
}): ExtractorCreateTarget => {
  const collectType = String(event.collect_type ?? '').trim();
  if (isTypeScopedCollectType(collectType)) {
    return { kind: 'type', collectType };
  }
  const instanceId = String(event.instance_id ?? '').trim();
  if (!instanceId || instanceId === 'base') {
    return { kind: 'unavailable', reason: 'missing_instance' };
  }
  return { kind: 'instance', instanceId };
};

export const buildTypeExtractorPath = (
  collectType: CollectTypeLinkFields,
  options?: { create?: boolean }
): string => {
  const params = new URLSearchParams({
    icon: String(collectType.icon || ''),
    name: collectType.name,
    collector: String(collectType.collector || ''),
    id: String(collectType.id ?? ''),
    display_name: String(collectType.display_name || collectType.name),
    description: String(
      collectType.display_description || collectType.description || '--'
    )
  });
  if (options?.create) params.set('create', '1');
  return `/log/integration/list/detail/extractor?${params.toString()}`;
};

export const buildInstanceExtractorPath = (
  instanceId: string,
  options?: { create?: boolean }
): string => {
  const params = new URLSearchParams({ extractor: instanceId });
  if (options?.create) params.set('create', '1');
  return `/log/integration/receive?${params.toString()}`;
};

export const extractorCreateSampleKey = (scope: {
  kind: 'type' | 'instance';
  id: string;
}): string => `${EXTRACTOR_CREATE_SAMPLE_STORAGE_KEY}:${scope.kind}:${scope.id}`;

export const storeExtractorCreateSample = (
  event: object,
  scope: { kind: 'type' | 'instance'; id: string }
): void => {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem(extractorCreateSampleKey(scope), JSON.stringify(event));
};

export const readExtractorCreateSample = (scope: {
  kind: 'type' | 'instance';
  id: string;
}): Record<string, unknown> | null => {
  if (typeof window === 'undefined') return null;
  const raw = sessionStorage.getItem(extractorCreateSampleKey(scope));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
};

export const consumeExtractorCreateSample = readExtractorCreateSample;

const EXTRACTOR_TYPE_LABEL_KEYS: Record<ExtractorType, string> = {
  copy: 'log.extractor.typeCopy',
  split: 'log.extractor.typeSplit',
  kv: 'log.extractor.typeKv',
  regex: 'log.extractor.typeRegex',
  regex_replace: 'log.extractor.typeRegexReplace',
  json: 'log.extractor.typeJson'
};

export const extractorTypeLabelKey = (type: ExtractorType): string =>
  EXTRACTOR_TYPE_LABEL_KEYS[type];

export const flattenExtractorPaths = (
  value: unknown,
  prefix = '',
  result = new Set<string>()
): Set<string> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return result;
  Object.entries(value).forEach(([key, child]) => {
    const segment = /^[A-Za-z_][A-Za-z0-9_]*$/.test(key)
      ? key
      : `[${JSON.stringify(key)}]`;
    const path = prefix
      ? segment.startsWith('[')
        ? `${prefix}${segment}`
        : `${prefix}.${segment}`
      : segment;
    result.add(path);
    flattenExtractorPaths(child, path, result);
  });
  return result;
};

export const normalizeExtractorSamples = (
  payload: unknown
): Record<string, unknown>[] => {
  if (Array.isArray(payload)) {
    return payload.filter(
      (item): item is Record<string, unknown> =>
        Boolean(item) && typeof item === 'object' && !Array.isArray(item)
    );
  }
  if (payload && typeof payload === 'object') {
    const data = (payload as Record<string, unknown>).data;
    if (Array.isArray(data)) return normalizeExtractorSamples(data);
  }
  return [];
};

export const moveExtractorItem = <T,>(
  items: T[],
  index: number,
  offset: -1 | 1
): T[] | null => {
  const target = index + offset;
  if (target < 0 || target >= items.length) return null;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
};

export const reorderExtractorItem = <T,>(
  items: T[],
  from: number,
  to: number
): T[] | null => {
  if (
    from === to ||
    from < 0 ||
    to < 0 ||
    from >= items.length ||
    to >= items.length
  ) {
    return null;
  }
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
};

export const shouldShowExtractorHeaderAdd = (
  canOperate: boolean | undefined,
  ruleCount: number
) => Boolean(canOperate) && ruleCount > 0;

export const shouldShowExtractorPublicationAlert = (
  status: 'pending' | 'generating' | 'published' | 'failed'
) => status !== 'published';
