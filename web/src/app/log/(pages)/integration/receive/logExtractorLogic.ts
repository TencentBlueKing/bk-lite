import type {
  ExtractorCondition,
  ExtractorConditionItem,
  ExtractorType
} from '@/app/log/types/extractor';

export const TYPE_SCOPED_COLLECT_TYPES = ['syslog', 'snmp_trap'] as const;
export const EXTRACTOR_CREATE_SAMPLE_STORAGE_KEY =
  'bk-lite.log-extractor.create-sample';
export const EXTRACTOR_CREATE_HANDOFF_STORAGE_KEY =
  'bk-lite.log-extractor.create-handoff';

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

export type ExtractorCreatePathOptions = {
  create?: boolean;
  handoff?: string;
  sourceField?: string;
};

export type ExtractorCreateHandoff = {
  event: Record<string, unknown>;
  source_field: string;
};

export type ExtractorPreviewFieldChange = {
  path: string;
  kind: 'added' | 'changed' | 'removed';
  before?: unknown;
  after?: unknown;
};

const appendExtractorCreateParams = (
  params: URLSearchParams,
  options?: ExtractorCreatePathOptions
) => {
  if (options?.create) params.set('create', '1');
  if (options?.handoff) params.set('handoff', options.handoff);
  if (options?.sourceField) params.set('source_field', options.sourceField);
};

export const buildTypeExtractorPath = (
  collectType: CollectTypeLinkFields,
  options?: ExtractorCreatePathOptions
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
  appendExtractorCreateParams(params, options);
  return `/log/integration/list/detail/extractor?${params.toString()}`;
};

export const buildInstanceExtractorPath = (
  instanceId: string,
  options?: ExtractorCreatePathOptions
): string => {
  const params = new URLSearchParams({ extractor: instanceId });
  appendExtractorCreateParams(params, options);
  return `/log/integration/receive?${params.toString()}`;
};

export const extractorCreateSampleKey = (scope: {
  kind: 'type' | 'instance';
  id: string;
}): string => `${EXTRACTOR_CREATE_SAMPLE_STORAGE_KEY}:${scope.kind}:${scope.id}`;

export const extractorCreateHandoffKey = (nonce: string): string =>
  `${EXTRACTOR_CREATE_HANDOFF_STORAGE_KEY}:${nonce}`;

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

export const restoreExtractorEventShape = (
  event: Record<string, unknown>
): Record<string, unknown> => {
  const restored: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(event)) {
    if (!key.includes('.')) restored[key] = value;
  }
  for (const [key, value] of Object.entries(event)) {
    if (!key.includes('.')) continue;
    const segments = key.split('.');
    if (!segments.every(Boolean)) {
      restored[key] = value;
      continue;
    }
    let current = restored;
    let conflict = false;
    for (const segment of segments.slice(0, -1)) {
      const existing = current[segment];
      if (existing == null) {
        const next: Record<string, unknown> = {};
        current[segment] = next;
        current = next;
        continue;
      }
      if (!isPlainObject(existing)) {
        conflict = true;
        break;
      }
      current = existing;
    }
    const leaf = segments[segments.length - 1];
    if (conflict || leaf in current) {
      restored[key] = value;
    } else {
      current[leaf] = value;
    }
  }
  return restored;
};

export const serializeExtractorCreateHandoff = (
  payload: ExtractorCreateHandoff
): string =>
  JSON.stringify({
    event: restoreExtractorEventShape(payload.event),
    source_field: payload.source_field
  });

export const parseExtractorCreateHandoff = (
  raw: string | null
): ExtractorCreateHandoff | null => {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!isPlainObject(parsed) || !isPlainObject(parsed.event)) return null;
    const sourceField = String(parsed.source_field || '').trim();
    if (!sourceField) return null;
    return {
      event: restoreExtractorEventShape(parsed.event),
      source_field: sourceField
    };
  } catch {
    return null;
  }
};

export const storeExtractorCreateHandoff = (
  payload: ExtractorCreateHandoff
): string => {
  const nonce =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(
      extractorCreateHandoffKey(nonce),
      serializeExtractorCreateHandoff(payload)
    );
  }
  return nonce;
};

export const consumeExtractorCreateHandoff = (
  nonce: string | null | undefined
): ExtractorCreateHandoff | null => {
  const id = String(nonce || '').trim();
  if (!id || typeof window === 'undefined') return null;
  const key = extractorCreateHandoffKey(id);
  const payload = parseExtractorCreateHandoff(window.localStorage.getItem(key));
  window.localStorage.removeItem(key);
  return payload;
};

export const storeExtractorCreateSample = (
  event: object,
  scope: { kind: 'type' | 'instance'; id: string }
): void => {
  if (typeof window === 'undefined' || !isPlainObject(event)) return;
  window.sessionStorage.setItem(
    extractorCreateSampleKey(scope),
    JSON.stringify(restoreExtractorEventShape(event))
  );
};

export const readExtractorCreateSample = (scope: {
  kind: 'type' | 'instance';
  id: string;
}): Record<string, unknown> | null => {
  if (typeof window === 'undefined') return null;
  try {
    const parsed = JSON.parse(
      window.sessionStorage.getItem(extractorCreateSampleKey(scope)) || 'null'
    ) as unknown;
    return isPlainObject(parsed) ? restoreExtractorEventShape(parsed) : null;
  } catch {
    return null;
  }
};

export const consumeExtractorCreateSample = (scope: {
  kind: 'type' | 'instance';
  id: string;
}): Record<string, unknown> | null => readExtractorCreateSample(scope);

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

export const extractorUsesSingleTargetField = (
  type?: ExtractorType | null
) => type === 'copy' || type === 'split' || type === 'regex_replace' || type === 'json';

export const extractorRequiresTargetField = (type?: ExtractorType | null) =>
  type === 'copy' || type === 'split';

export const flattenExtractorLeafValues = (
  value: unknown,
  prefix = '',
  result = new Map<string, unknown>()
): Map<string, unknown> => {
  if (!isPlainObject(value)) {
    if (prefix) result.set(prefix, value);
    return result;
  }
  const entries = Object.entries(value);
  if (!entries.length) {
    if (prefix) result.set(prefix, value);
    return result;
  }
  entries.forEach(([key, child]) => {
    const segment = /^[A-Za-z_][A-Za-z0-9_]*$/.test(key)
      ? key
      : `[${JSON.stringify(key)}]`;
    const path = prefix
      ? segment.startsWith('[')
        ? `${prefix}${segment}`
        : `${prefix}.${segment}`
      : segment;
    if (isPlainObject(child) && Object.keys(child).length) {
      flattenExtractorLeafValues(child, path, result);
      return;
    }
    result.set(path, child);
  });
  return result;
};

const sameExtractorPreviewValue = (left: unknown, right: unknown) =>
  Object.is(left, right) || JSON.stringify(left) === JSON.stringify(right);

export const diffExtractorPreviewFields = (
  before: Record<string, unknown> | null | undefined,
  after: Record<string, unknown> | null | undefined
): ExtractorPreviewFieldChange[] => {
  const beforeMap = flattenExtractorLeafValues(before || {});
  const afterMap = flattenExtractorLeafValues(after || {});
  const changes: ExtractorPreviewFieldChange[] = [];
  afterMap.forEach((value, path) => {
    if (!beforeMap.has(path)) {
      changes.push({ path, kind: 'added', after: value });
      return;
    }
    if (!sameExtractorPreviewValue(beforeMap.get(path), value)) {
      changes.push({
        path,
        kind: 'changed',
        before: beforeMap.get(path),
        after: value
      });
    }
  });
  beforeMap.forEach((value, path) => {
    if (!afterMap.has(path)) {
      changes.push({ path, kind: 'removed', before: value });
    }
  });
  return changes;
};

export const formatExtractorPreviewValue = (value: unknown) => {
  if (typeof value === 'string') return value;
  if (value === undefined) return 'undefined';
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

const PREVIEW_STATUS_LABEL_KEYS = {
  success: 'log.extractor.previewStatusSuccess',
  not_matched: 'log.extractor.previewStatusNotMatched',
  skipped: 'log.extractor.previewStatusSkipped',
  failed: 'log.extractor.previewStatusFailed'
} as const;

export const extractorPreviewStatusLabelKey = (
  status: keyof typeof PREVIEW_STATUS_LABEL_KEYS | string
) =>
  PREVIEW_STATUS_LABEL_KEYS[status as keyof typeof PREVIEW_STATUS_LABEL_KEYS] ||
  PREVIEW_STATUS_LABEL_KEYS.failed;

export const EXTRACTOR_CONDITION_OPERATORS = [
  '==',
  '!=',
  'contains',
  '!contains',
  'startswith',
  'endswith'
] as const;

export type ExtractorConditionOperator =
  (typeof EXTRACTOR_CONDITION_OPERATORS)[number];

const EXTRACTOR_CONDITION_OPERATOR_LABEL_KEYS: Record<
  ExtractorConditionOperator,
  string
> = {
  '==': 'log.extractor.conditionOpEq',
  '!=': 'log.extractor.conditionOpNe',
  contains: 'log.extractor.conditionOpContains',
  '!contains': 'log.extractor.conditionOpNotContains',
  startswith: 'log.extractor.conditionOpStartsWith',
  endswith: 'log.extractor.conditionOpEndsWith'
};

export const isExtractorConditionOperator = (
  value: unknown
): value is ExtractorConditionOperator =>
  EXTRACTOR_CONDITION_OPERATORS.includes(value as ExtractorConditionOperator);

export const extractorConditionOperatorLabelKey = (
  op: ExtractorConditionItem['op'] | ExtractorConditionOperator
) =>
  EXTRACTOR_CONDITION_OPERATOR_LABEL_KEYS[op as ExtractorConditionOperator] ||
  (op === 'exists'
    ? 'log.extractor.conditionOpExists'
    : op === '!exists'
      ? 'log.extractor.conditionOpNotExists'
      : 'log.extractor.condition');

export const extractorConditionNeedsValue = (op: unknown) =>
  op !== 'exists' && op !== '!exists';

export const extractorConditionModeLabelKey = (mode: 'AND' | 'OR') =>
  mode === 'OR'
    ? 'log.extractor.conditionModeOr'
    : 'log.extractor.conditionModeAnd';

export const emptyExtractorCondition = (): ExtractorCondition => ({
  mode: 'AND',
  conditions: []
});

export const defaultExtractorConditionItem = (): ExtractorConditionItem => ({
  field: 'message',
  op: '==',
  value: ''
});

export const normalizeExtractorCondition = (input: {
  mode?: string | null;
  conditions?: Array<{
    field?: string;
    op?: string;
    value?: unknown;
  }> | null;
}): ExtractorCondition => {
  const conditions: ExtractorConditionItem[] = [];
  for (const item of input.conditions || []) {
    const field = String(item.field || '').trim();
    const op = item.op;
    if (!field || !isExtractorConditionOperator(op)) continue;
    const value = item.value;
    conditions.push({
      field,
      op,
      value:
        typeof value === 'string' ||
        typeof value === 'number' ||
        typeof value === 'boolean'
          ? value
          : value == null
            ? ''
            : String(value)
    });
  }
  return {
    mode: input.mode === 'OR' ? 'OR' : 'AND',
    conditions
  };
};

export const getExtractorConditionSummary = (
  condition?: ExtractorCondition | null
): { mode: 'AND' | 'OR'; items: ExtractorConditionItem[] } | null => {
  const items = condition?.conditions || [];
  if (!items.length) return null;
  return {
    mode: condition?.mode === 'OR' ? 'OR' : 'AND',
    items
  };
};
