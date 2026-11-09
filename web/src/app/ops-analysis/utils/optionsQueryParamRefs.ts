import type {
  DynamicOptionsSource,
  InputControlConfig,
  OptionsQueryParamValue,
} from '@/app/ops-analysis/types/dataSource';
import { isBindableDataSourceParamType } from '@/app/ops-analysis/utils/dataSourceParamContract';

/** 依赖链最多 3 个参数（A→B→C）。A→B→C→D 拒绝。 */
export const MAX_OPTIONS_QUERY_CHAIN_NODES = 3;

const WHOLE_TOKEN = /^\$([A-Za-z_][\w-]*)(?::(string|number|boolean|date|timeRange|dateRange))?\$/;

export interface OptionsQueryParamRef {
  ref: string;
}

export type OptionsQueryValidationIssue =
  | { code: 'concat'; param: string; name?: string }
  | { code: 'invalid'; param: string; name?: string }
  | { code: 'self'; name: string; ref?: string; param?: string }
  | { code: 'missing'; name: string; ref: string; param?: string }
  | { code: 'type'; name: string; ref: string; param?: string }
  | { code: 'ambiguous'; name: string; ref: string; param?: string }
  | { code: 'cycle'; path: string[]; name: string; ref: string; param: string }
  | { code: 'depth'; path: string[]; name: string; ref: string; param: string };

export interface OptionsQueryKnownName {
  name: string;
  type?: string;
}

export interface OptionsQueryNode {
  /** 图节点。同名多行时用 definition.id，唯一行可用参数名。 */
  name: string;
  /** 参数名。多个节点共用同一个别名时，按参数名引用会被拒绝。 */
  aliases?: string[];
  queryParams?: Record<string, unknown>;
}

export type OptionsQueryBlockReason = 'empty' | 'invalid';

export interface ResolvedOptionsQuery {
  blocked: boolean;
  blockReason?: OptionsQueryBlockReason;
  params: Record<string, unknown>;
  missingRefs: string[];
}

/** lookup 返回这个标记表示引用无法对应到唯一上游，而不是上游值为空。 */
export const OPTIONS_QUERY_INVALID = Symbol('optionsQueryInvalid');

export const readOptionsQueryUpstream = (
  ref: string,
  definitions: Array<{ id: string; key: string; enabled?: boolean }>,
  readValue: (id: string) => unknown,
): { found: true; invalid: true } | { found: true; invalid: false; value: unknown } | { found: false } => {
  const enabled = definitions.filter((item) => item.enabled !== false);
  const byId = enabled.find((item) => item.id === ref);
  if (byId) return { found: true, invalid: false, value: readValue(byId.id) };
  const byKey = enabled.filter((item) => item.key === ref);
  if (byKey.length > 1) return { found: true, invalid: true };
  if (byKey.length === 1) return { found: true, invalid: false, value: readValue(byKey[0].id) };
  return { found: false };
};

/**
 * 裸参数名在保存或布局同步时收成筛选 id。
 * 同名只有一条时用那条；多条时只接受与引用方同一数据源的那条。对不上就保持原样。
 */
export const resolveBareFilterRef = <T extends { id: string; key: string; enabled?: boolean }>(
  ref: string,
  ownerId: string,
  definitions: T[],
  origins: ReadonlyMap<string, readonly number[]> = new Map(),
): string => {
  const trimmed = ref.trim();
  if (!trimmed) return trimmed;
  if (definitions.some((item) => item.enabled !== false && item.id === trimmed)) return trimmed;
  const hits = definitions.filter((item) =>
    item.enabled !== false && item.id !== ownerId && item.key === trimmed);
  if (hits.length === 1) return hits[0].id;
  if (hits.length < 2) return trimmed;
  const ownerSources = origins.get(ownerId) ?? [];
  if (!ownerSources.length) return trimmed;
  const linked = hits.filter((item) =>
    (origins.get(item.id) ?? []).some((id) => ownerSources.includes(id)));
  return linked.length === 1 ? linked[0].id : trimmed;
};

const dynamicOptionsOf = (
  inputConfig: InputControlConfig | undefined,
): DynamicOptionsSource | undefined => {
  if (!inputConfig || (inputConfig.control !== 'select' && inputConfig.control !== 'radio')) {
    return undefined;
  }
  return inputConfig.optionsSource.type === 'dynamic' ? inputConfig.optionsSource : undefined;
};

const RETIRED_SUMMARY_REF = /^(.+)__[0-9a-f]{8}$/;

/**
 * 拆行期摘要 id（`name__type` 再加 8 位摘要）在并回一行后不再存在。
 * 新定义里已经有 `name__type`、且旧 id 不在时，把引用改到这一行。旧 id 仍在则保持。
 */
export const redirectRetiredSummaryRef = (
  ref: string,
  liveIds: ReadonlySet<string>,
): string => {
  if (liveIds.has(ref)) return ref;
  const match = RETIRED_SUMMARY_REF.exec(ref);
  if (!match) return ref;
  const canonical = match[1];
  return liveIds.has(canonical) ? canonical : ref;
};

const rewriteQueryParamRecord = (
  queryParams: Record<string, unknown>,
  liveIds: ReadonlySet<string>,
): Record<string, unknown> => {
  let changed = false;
  const next: Record<string, unknown> = { ...queryParams };
  Object.entries(queryParams).forEach(([name, raw]) => {
    if (!isOptionsQueryParamRef(raw)) return;
    const redirected = redirectRetiredSummaryRef(raw.ref, liveIds);
    if (redirected === raw.ref) return;
    next[name] = { ref: redirected };
    changed = true;
  });
  return changed ? next : queryParams;
};

export const rewriteInputConfigRetiredSummaryRefs = <T extends InputControlConfig | undefined>(
  inputConfig: T,
  liveIds: ReadonlySet<string>,
): T => {
  if (!inputConfig || liveIds.size === 0) return inputConfig;
  const source = dynamicOptionsOf(inputConfig);
  if (!source?.queryParams) return inputConfig;
  const queryParams = rewriteQueryParamRecord(source.queryParams, liveIds);
  if (queryParams === source.queryParams) return inputConfig;
  return {
    ...inputConfig,
    optionsSource: { ...source, queryParams },
  } as T;
};

export const rewriteDefinitionQueryRefs = <T extends { inputConfig?: InputControlConfig }>(
  definitions: T[],
  liveIds: ReadonlySet<string>,
): T[] => {
  if (!definitions.length || liveIds.size === 0) return definitions;
  let changed = false;
  const next = definitions.map((definition) => {
    const inputConfig = rewriteInputConfigRetiredSummaryRefs(definition.inputConfig, liveIds);
    if (inputConfig === definition.inputConfig) return definition;
    changed = true;
    return { ...definition, inputConfig };
  });
  return changed ? next : definitions;
};

export const rewriteParamQueryRefs = <T extends { inputConfig?: InputControlConfig }>(
  params: T[] | undefined,
  liveIds: ReadonlySet<string>,
): T[] | undefined => {
  if (!params?.length || liveIds.size === 0) return params;
  let changed = false;
  const next = params.map((param) => {
    const inputConfig = rewriteInputConfigRetiredSummaryRefs(param.inputConfig, liveIds);
    if (inputConfig === param.inputConfig) return param;
    changed = true;
    return { ...param, inputConfig };
  });
  return changed ? next : params;
};

/** 把定义上的裸名引用收成筛选 id。没有变化时返回原数组。 */
export const rewriteBareQueryRefsToDefinitionIds = <T extends {
  id: string; key: string; enabled?: boolean; inputConfig?: InputControlConfig;
}>(definitions: T[], origins: ReadonlyMap<string, readonly number[]> = new Map()): T[] => {
  let changed = false;
  const next = definitions.map((definition) => {
    const source = dynamicOptionsOf(definition.inputConfig);
    if (!source?.queryParams || !definition.inputConfig) return definition;
    let queryChanged = false;
    const queryParams = { ...source.queryParams };
    Object.entries(source.queryParams).forEach(([name, raw]) => {
      if (!isOptionsQueryParamRef(raw)) return;
      const resolved = resolveBareFilterRef(raw.ref, definition.id, definitions, origins);
      if (resolved === raw.ref) return;
      queryParams[name] = { ref: resolved };
      queryChanged = true;
    });
    if (!queryChanged) return definition;
    changed = true;
    const inputConfig = {
      ...definition.inputConfig,
      optionsSource: { ...source, queryParams },
    } as InputControlConfig;
    return { ...definition, inputConfig };
  });
  return changed ? next : definitions;
};

/** 已经命中某一行时：同名裸引用返回非法标记，否则返回该行的值。 */
export const valueOfFoundOptionsQueryUpstream = (
  upstream: { invalid: true } | { invalid: false; value: unknown },
): unknown => (upstream.invalid === true ? OPTIONS_QUERY_INVALID : upstream.value);

export const stableStringify = (value: unknown): string => {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`;
  }
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
    .join(',')}}`;
};

export const isOptionsQueryParamRef = (value: unknown): value is OptionsQueryParamRef => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return typeof record.ref === 'string' && record.ref.trim().length > 0 && Object.keys(record).length === 1;
};

export const parseWholeOptionsQueryToken = (value: string): OptionsQueryParamRef | null => {
  const match = WHOLE_TOKEN.exec(value);
  if (!match || match[0] !== value) return null;
  return { ref: match[1] };
};

export const isUpstreamValueEmpty = (value: unknown): boolean => {
  if (value === null || value === undefined || value === '') return true;
  return Array.isArray(value) && value.length === 0;
};

type NormalizedQueryParam =
  | { ok: true; value: OptionsQueryParamValue }
  | { ok: false; reason: 'concat' | 'invalid' };

type StoredQueryParams =
  | { ok: true; queryParams?: Record<string, OptionsQueryParamValue> }
  | { ok: false; issue: OptionsQueryValidationIssue };

const isRejectedQueryParam = (
  result: NormalizedQueryParam,
): result is { ok: false; reason: 'concat' | 'invalid' } => result.ok === false;

export const isRejectedQueryParams = (
  result: StoredQueryParams,
): result is { ok: false; issue: OptionsQueryValidationIssue } => result.ok === false;

export const normalizeOptionsQueryParamValue = (
  value: unknown,
): NormalizedQueryParam => {
  if (typeof value === 'number' || typeof value === 'boolean' || value === null) {
    return { ok: true, value: value as OptionsQueryParamValue };
  }
  if (isOptionsQueryParamRef(value)) return { ok: true, value: { ref: value.ref } };
  if (typeof value === 'string') {
    if (value.includes('$')) {
      const token = parseWholeOptionsQueryToken(value);
      if (!token) return { ok: false, reason: 'concat' };
      return { ok: true, value: token };
    }
    return { ok: true, value };
  }
  return { ok: false, reason: 'invalid' };
};

export const normalizeQueryParamsForStorage = (
  queryParams?: Record<string, unknown>,
): StoredQueryParams => {
  if (!queryParams) return { ok: true };
  const next: Record<string, OptionsQueryParamValue> = {};
  for (const [name, raw] of Object.entries(queryParams)) {
    if (!name.trim()) continue;
    const normalized = normalizeOptionsQueryParamValue(raw);
    if (isRejectedQueryParam(normalized)) {
      return {
        ok: false,
        issue: { code: normalized.reason, param: name },
      };
    }
    next[name] = normalized.value;
  }
  return { ok: true, queryParams: Object.keys(next).length ? next : undefined };
};

export const collectQueryParamRefs = (
  queryParams?: Record<string, unknown>,
): string[] => {
  if (!queryParams) return [];
  const refs = new Set<string>();
  Object.values(queryParams).forEach((raw) => {
    const normalized = normalizeOptionsQueryParamValue(raw);
    if (normalized.ok && isOptionsQueryParamRef(normalized.value)) refs.add(normalized.value.ref);
  });
  return Array.from(refs).sort();
};

export const collectQueryParamLiterals = (
  queryParams?: Record<string, unknown>,
): Record<string, string | number | boolean | null> => {
  if (!queryParams) return {};
  const literals: Record<string, string | number | boolean | null> = {};
  Object.entries(queryParams).forEach(([name, raw]) => {
    const normalized = normalizeOptionsQueryParamValue(raw);
    if (!normalized.ok) {
      if (typeof raw === 'string') literals[name] = raw;
      return;
    }
    if (!isOptionsQueryParamRef(normalized.value)) literals[name] = normalized.value;
  });
  return literals;
};

/** 配置键用的查询入参结构：引用名和字面量，不含运行时上游值。 */
export const canonicalQueryParams = (
  queryParams?: Record<string, unknown>,
): { refs: string[]; literals: Record<string, string | number | boolean | null> } | null => {
  if (!queryParams || Object.keys(queryParams).length === 0) return null;
  return {
    refs: collectQueryParamRefs(queryParams),
    literals: collectQueryParamLiterals(queryParams),
  };
};

const nodesForRef = (nodes: OptionsQueryNode[], ref: string): OptionsQueryNode[] => {
  const direct = nodes.filter((node) => node.name === ref);
  const aliased = nodes.filter((node) => node.aliases?.includes(ref) && node.name !== ref);
  return [...direct, ...aliased];
};

interface QueryGraphEdge {
  from: string;
  to: string;
  ref: string;
  param: string;
}

const knownNameMap = (knownNames: Array<string | OptionsQueryKnownName>) => {
  const known = new Map<string, string | undefined>();
  knownNames.forEach((entry) => {
    if (!entry) return;
    if (typeof entry === 'string') {
      if (!known.has(entry)) known.set(entry, undefined);
      return;
    }
    if (!entry.name) return;
    const previous = known.get(entry.name);
    known.set(entry.name, entry.type || previous);
  });
  return known;
};

/** 有向图的强连通分量。多于一个节点的分量里的边构成环。 */
const stronglyConnectedComponents = (
  names: string[],
  adjacent: Map<string, string[]>,
): string[][] => {
  let index = 0;
  const indices = new Map<string, number>();
  const low = new Map<string, number>();
  const stack: string[] = [];
  const onStack = new Set<string>();
  const components: string[][] = [];
  const visit = (name: string) => {
    indices.set(name, index);
    low.set(name, index);
    index += 1;
    stack.push(name);
    onStack.add(name);
    (adjacent.get(name) ?? []).forEach((next) => {
      if (!indices.has(next)) {
        visit(next);
        low.set(name, Math.min(low.get(name) ?? 0, low.get(next) ?? 0));
        return;
      }
      if (onStack.has(next)) {
        low.set(name, Math.min(low.get(name) ?? 0, indices.get(next) ?? 0));
      }
    });
    if (low.get(name) !== indices.get(name)) return;
    const component: string[] = [];
    let member = '';
    do {
      member = stack.pop() ?? '';
      onStack.delete(member);
      component.push(member);
    } while (member !== name);
    components.push(component);
  };
  names.forEach((name) => {
    if (!indices.has(name)) visit(name);
  });
  return components;
};

const longestDependencyPath = (
  name: string,
  adjacent: Map<string, string[]>,
): string[] => {
  const children = adjacent.get(name) ?? [];
  let best: string[] = [];
  children.forEach((child) => {
    const path = longestDependencyPath(child, adjacent);
    if (path.length > best.length) best = path;
  });
  return [name, ...best];
};

/**
 * 一次扫完全部引用问题。超长链只标出超出 3 级的那条边，不把仍合法的前缀算进去。
 * 环上的边单独标出，不顺着环继续算级数。
 */
export const collectOptionsQueryParamIssues = (
  nodes: OptionsQueryNode[],
  knownNames: Array<string | OptionsQueryKnownName>,
): OptionsQueryValidationIssue[] => {
  const known = knownNameMap(knownNames);
  const issues: OptionsQueryValidationIssue[] = [];
  const edges: QueryGraphEdge[] = [];

  nodes.forEach((node) => {
    if (!node.name || !node.queryParams) return;
    Object.entries(node.queryParams).forEach(([param, raw]) => {
      const normalized = normalizeOptionsQueryParamValue(raw);
      if (isRejectedQueryParam(normalized)) {
        issues.push({ code: normalized.reason, param, name: node.name });
        return;
      }
      if (!isOptionsQueryParamRef(normalized.value)) return;
      const ref = normalized.value.ref;
      if (ref === node.name) {
        issues.push({ code: 'self', name: node.name, ref, param });
        return;
      }
      const targets = nodesForRef(nodes, ref);
      if (targets.length > 1) {
        issues.push({ code: 'ambiguous', name: node.name, ref, param });
        return;
      }
      if (targets.length === 1 && targets[0].name === node.name) {
        issues.push({ code: 'self', name: node.name, ref, param });
        return;
      }
      const resolved = targets.length === 1 ? targets[0].name : ref;
      if (known.size > 0 && !known.has(ref) && !known.has(resolved) && targets.length === 0) {
        issues.push({ code: 'missing', name: node.name, ref, param });
        return;
      }
      const targetType = known.get(ref) || known.get(resolved);
      if (targetType && !isBindableDataSourceParamType(targetType)) {
        issues.push({ code: 'type', name: node.name, ref, param });
        return;
      }
      edges.push({ from: node.name, to: resolved, ref, param });
    });
  });

  const names = Array.from(new Set([
    ...nodes.flatMap((node) => (node.name ? [node.name] : [])),
    ...edges.flatMap((edge) => [edge.from, edge.to]),
  ]));
  const adjacent = new Map<string, string[]>();
  edges.forEach((edge) => {
    const next = adjacent.get(edge.from) ?? [];
    next.push(edge.to);
    adjacent.set(edge.from, next);
  });
  const components = stronglyConnectedComponents(names, adjacent);
  const componentOf = new Map<string, number>();
  components.forEach((component, index) => {
    if (component.length <= 1) return;
    component.forEach((name) => componentOf.set(name, index));
  });

  const dag = new Map<string, string[]>();
  edges.forEach((edge) => {
    const group = componentOf.get(edge.from);
    if (group !== undefined && group === componentOf.get(edge.to)) {
      const component = components[group] ?? [];
      issues.push({
        code: 'cycle',
        name: edge.from,
        ref: edge.ref,
        param: edge.param,
        path: component.length ? [...component, component[0]] : [edge.from, edge.to, edge.from],
      });
      return;
    }
    const next = dag.get(edge.from) ?? [];
    next.push(edge.to);
    dag.set(edge.from, next);
  });

  const chainLength = new Map<string, number>();
  const measure = (name: string): number => {
    const cached = chainLength.get(name);
    if (cached !== undefined) return cached;
    chainLength.set(name, 1);
    const longest = (dag.get(name) ?? []).reduce(
      (max, child) => Math.max(max, 1 + measure(child)),
      1,
    );
    chainLength.set(name, longest);
    return longest;
  };

  edges.forEach((edge) => {
    const group = componentOf.get(edge.from);
    if (group !== undefined && group === componentOf.get(edge.to)) return;
    if (1 + measure(edge.to) <= MAX_OPTIONS_QUERY_CHAIN_NODES) return;
    issues.push({
      code: 'depth',
      name: edge.from,
      ref: edge.ref,
      param: edge.param,
      path: [edge.from, ...longestDependencyPath(edge.to, dag)],
    });
  });
  return issues;
};

export const validateOptionsQueryParams = (
  nodes: OptionsQueryNode[],
  knownNames: Array<string | OptionsQueryKnownName>,
): OptionsQueryValidationIssue | null => collectOptionsQueryParamIssues(nodes, knownNames)[0] ?? null;

/** 丢掉被点名的查询入参键，其余字面量和仍合法的引用留下。 */
export const withoutRejectedQueryParams = (
  queryParams: Record<string, unknown> | undefined,
  rejectedParams: Set<string>,
): Record<string, OptionsQueryParamValue> | undefined => {
  if (!queryParams) return undefined;
  const next: Record<string, OptionsQueryParamValue> = {};
  Object.entries(queryParams).forEach(([key, raw]) => {
    if (rejectedParams.has(key)) return;
    const normalized = normalizeOptionsQueryParamValue(raw);
    if (isRejectedQueryParam(normalized)) return;
    next[key] = normalized.value;
  });
  return Object.keys(next).length ? next : undefined;
};

const filterQueryGraph = (
  definitions: Array<{
    id: string;
    key: string;
    type?: string;
    inputConfig?: { control?: string; optionsSource?: { type?: string; queryParams?: Record<string, unknown> } };
  }>,
) => ({
  nodes: definitions.map((item) => ({
    name: item.id,
    aliases: item.key && item.key !== item.id ? [item.key] : undefined,
    queryParams: dynamicQueryParamsOf(item.inputConfig),
  })),
  known: definitions.flatMap((item) => [
    { name: item.id, type: item.type },
    ...(item.key ? [{ name: item.key, type: item.type }] : []),
  ]),
});

export const collectUnifiedFilterQueryIssues = (
  definitions: Array<{
    id: string;
    key: string;
    type?: string;
    inputConfig?: { control?: string; optionsSource?: { type?: string; queryParams?: Record<string, unknown> } };
  }>,
): OptionsQueryValidationIssue[] => {
  const graph = filterQueryGraph(definitions);
  return collectOptionsQueryParamIssues(graph.nodes, graph.known);
};

export const validateUnifiedFilterQueryGraph = (
  definitions: Array<{
    id: string;
    key: string;
    type?: string;
    inputConfig?: { control?: string; optionsSource?: { type?: string; queryParams?: Record<string, unknown> } };
  }>,
): OptionsQueryValidationIssue | null => collectUnifiedFilterQueryIssues(definitions)[0] ?? null;

export const resolveOptionsQueryParams = (
  queryParams: Record<string, unknown> | undefined,
  lookup: (ref: string) => unknown,
): ResolvedOptionsQuery => {
  if (!queryParams || Object.keys(queryParams).length === 0) {
    return { blocked: false, params: {}, missingRefs: [] };
  }
  const params: Record<string, unknown> = {};
  const missingRefs: string[] = [];
  for (const [name, raw] of Object.entries(queryParams)) {
    const normalized = normalizeOptionsQueryParamValue(raw);
    if (isRejectedQueryParam(normalized)) {
      return { blocked: true, blockReason: 'invalid', params: {}, missingRefs: [] };
    }
    if (isOptionsQueryParamRef(normalized.value)) {
      const upstream = lookup(normalized.value.ref);
      if (upstream === OPTIONS_QUERY_INVALID) {
        return { blocked: true, blockReason: 'invalid', params: {}, missingRefs: [] };
      }
      if (isUpstreamValueEmpty(upstream)) missingRefs.push(normalized.value.ref);
      else params[name] = upstream;
    } else {
      params[name] = normalized.value;
    }
  }
  if (missingRefs.length) {
    return { blocked: true, blockReason: 'empty', params: {}, missingRefs };
  }
  return { blocked: false, params, missingRefs: [] };
};

export const dynamicQueryParamsOf = (
  inputConfig: { control?: string; optionsSource?: { type?: string; queryParams?: Record<string, unknown> } } | undefined,
): Record<string, unknown> | undefined => {
  if (!inputConfig || (inputConfig.control !== 'select' && inputConfig.control !== 'radio')) {
    return undefined;
  }
  const source = inputConfig.optionsSource;
  if (!source || source.type !== 'dynamic') return undefined;
  return source.queryParams;
};

/** 选项查询里只要有引用，组件内切换就不能开。 */
export const hasOptionsQueryRef = (
  inputConfig: { control?: string; optionsSource?: { type?: string; queryParams?: Record<string, unknown> } } | undefined,
): boolean => collectQueryParamRefs(dynamicQueryParamsOf(inputConfig)).length > 0;
