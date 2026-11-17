import type { InputControlConfig } from '@/app/ops-analysis/types/dataSource';

export const DATA_VARIABLE_ROW_LIMIT = 10_000;
export const DATA_VARIABLE_MAX_DEPTH = 3;

export interface DataVariableRef {
  dataVariableId: string;
}

export interface DataVariable {
  id: string;
  name: string;
  dataSourceId: number;
  valueField: string;
  params: Record<string, unknown>;
  /** 和组件一样：开着的筛选用页头当前值。缺省表示还没配过。 */
  filterBindings?: Record<string, boolean>;
  /** 查询参数的输入方式。数据变量引用记在 control=dataVariable。 */
  paramInputs?: Record<string, InputControlConfig>;
}

export type ColumnBlockReason =
  | 'empty'
  | 'nodata'
  | 'shape'
  | 'cell'
  | 'missing-field'
  | 'too-many'
  | 'upstream'
  | 'request';

/** 查询还没发出去就停住。和接口失败分开，避免必填项没填被说成查询失败。 */
export class DataVariableBlocked extends Error {
  readonly reason: ColumnBlockReason;

  constructor(reason: ColumnBlockReason) {
    super(reason);
    this.name = 'DataVariableBlocked';
    this.reason = reason;
  }
}

export type ColumnResult =
  | { status: 'ready'; values: unknown[] }
  | { status: 'blocked'; reason: ColumnBlockReason };

export type DataVariableIssueCode =
  | 'duplicate-name'
  | 'missing-name'
  | 'missing-value-field'
  | 'missing-datasource'
  | 'cycle'
  | 'too-deep'
  | 'unknown-variable';

export interface DataVariableIssue {
  code: DataVariableIssueCode;
  id?: string;
  name?: string;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

export const isDataVariableRef = (value: unknown): value is DataVariableRef =>
  isRecord(value)
  && typeof value.dataVariableId === 'string'
  && Object.keys(value).length === 1;

const readFilterBindings = (raw: unknown): Record<string, boolean> | undefined => {
  if (!isRecord(raw)) return undefined;
  const bindings: Record<string, boolean> = {};
  Object.entries(raw).forEach(([id, enabled]) => {
    if (typeof enabled === 'boolean') bindings[id] = enabled;
  });
  return Object.keys(bindings).length > 0 ? bindings : undefined;
};

const readParamInputs = (
  raw: unknown,
): DataVariable['paramInputs'] => {
  if (!isRecord(raw)) return undefined;
  const inputs: NonNullable<DataVariable['paramInputs']> = {};
  Object.entries(raw).forEach(([name, value]) => {
    if (!isRecord(value) || typeof value.control !== 'string') return;
    if (value.control === 'dataVariable') {
      if (typeof value.dataVariableId !== 'string' || value.dataVariableId === '') return;
      inputs[name] = { control: 'dataVariable', dataVariableId: value.dataVariableId };
      return;
    }
    inputs[name] = value as InputControlConfig;
  });
  return Object.keys(inputs).length > 0 ? inputs : undefined;
};

export const isEmptyParamValue = (value: unknown): boolean =>
  value == null || value === '' || (Array.isArray(value) && value.length === 0);

/** 目录里标了必填、整好的请求里仍然没有值。 */
export const missingRequiredParam = (
  catalog: Array<{ name?: string; required?: boolean }> | undefined,
  params: Record<string, unknown>,
): boolean => Array.isArray(catalog) && catalog.some((param) => (
  param.required === true
  && typeof param.name === 'string'
  && isEmptyParamValue(params[param.name])
));

const isConditionGroup = (value: unknown): value is { logic?: unknown; items: unknown[] } =>
  isRecord(value)
  && Array.isArray(value.items)
  && (value.logic === 'AND' || value.logic === 'OR' || value.logic === undefined);

export const readDataVariables = (raw: unknown): DataVariable[] => {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    if (!isRecord(item)) return [];
    const id = typeof item.id === 'string' ? item.id.trim() : '';
    const name = typeof item.name === 'string' ? item.name.trim() : '';
    const dataSourceId = typeof item.dataSourceId === 'number' && Number.isInteger(item.dataSourceId)
      ? item.dataSourceId
      : 0;
    const valueField = typeof item.valueField === 'string' ? item.valueField.trim() : '';
    const params = isRecord(item.params) ? item.params : {};
    const filterBindings = readFilterBindings(item.filterBindings);
    const paramInputs = readParamInputs(item.paramInputs);
    if (!id) return [];
    return [{
      id,
      name,
      dataSourceId,
      valueField,
      params,
      ...(filterBindings ? { filterBindings } : {}),
      ...(paramInputs ? { paramInputs } : {}),
    }];
  });
};

export const createDataVariableId = (): string => {
  const uuid = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  return `dv_${uuid}`;
};

const copyJson = <T>(value: T): T => (
  value === undefined ? value : JSON.parse(JSON.stringify(value)) as T
);

/** 从组件当前查询拷一份数据变量。名称和取值列由调用方另填。 */
export const widgetQueryToDataVariable = ({
  name,
  valueField,
  dataSourceId,
  params,
  filterBindings,
  paramInputs,
}: {
  name: string;
  valueField: string;
  dataSourceId: number;
  params: Record<string, unknown>;
  filterBindings?: Record<string, boolean>;
  paramInputs?: DataVariable['paramInputs'];
}): DataVariable => {
  const bindings = readFilterBindings(copyJson(filterBindings));
  const inputs = readParamInputs(copyJson(paramInputs));
  return {
    id: createDataVariableId(),
    name: name.trim(),
    dataSourceId,
    valueField: valueField.trim(),
    params: copyJson(params),
    ...(bindings ? { filterBindings: bindings } : {}),
    ...(inputs ? { paramInputs: inputs } : {}),
  };
};

const referencedIdsIn = (value: unknown, into: Set<string>) => {
  if (isDataVariableRef(value)) {
    into.add(value.dataVariableId);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => referencedIdsIn(item, into));
    return;
  }
  if (!isRecord(value)) return;
  Object.values(value).forEach((item) => referencedIdsIn(item, into));
};

export const collectVariableIds = (value: unknown): string[] => {
  const ids = new Set<string>();
  referencedIdsIn(value, ids);
  return [...ids];
};

const directDependencies = (variable: DataVariable): string[] => {
  const ids = new Set(collectVariableIds(variable.params));
  Object.values(variable.paramInputs ?? {}).forEach((input) => {
    if (input.control === 'dataVariable') ids.add(input.dataVariableId);
  });
  return [...ids];
};

/** 查询相关字段。改名称不重新请求。 */
export const variableQueryKey = (variable: DataVariable): string => JSON.stringify({
  dataSourceId: variable.dataSourceId,
  valueField: variable.valueField,
  params: variable.params,
  filterBindings: variable.filterBindings ?? null,
  paramInputs: variable.paramInputs ?? null,
});

/** 被改动的变量，以及参数里引用了它们的下游。 */
export const variablesAffectedBy = (
  variables: DataVariable[],
  changedIds: readonly string[],
): string[] => {
  const dependents = new Map<string, string[]>();
  variables.forEach((variable) => {
    directDependencies(variable).forEach((refId) => {
      const list = dependents.get(refId) ?? [];
      list.push(variable.id);
      dependents.set(refId, list);
    });
  });
  const seen = new Set<string>();
  const queue = [...changedIds];
  while (queue.length > 0) {
    const id = queue.shift();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    (dependents.get(id) ?? []).forEach((child) => queue.push(child));
  }
  return [...seen];
};

export const validateDataVariables = (variables: DataVariable[]): DataVariableIssue[] => {
  const issues: DataVariableIssue[] = [];
  const seenNames = new Set<string>();
  const byId = new Map(variables.map((variable) => [variable.id, variable]));

  variables.forEach((variable) => {
    if (!variable.name) issues.push({ code: 'missing-name', id: variable.id });
    if (variable.name) {
      if (seenNames.has(variable.name)) issues.push({ code: 'duplicate-name', id: variable.id, name: variable.name });
      seenNames.add(variable.name);
    }
    if (!variable.valueField) issues.push({ code: 'missing-value-field', id: variable.id });
    if (!variable.dataSourceId) issues.push({ code: 'missing-datasource', id: variable.id });
    directDependencies(variable).forEach((refId) => {
      if (!byId.has(refId)) issues.push({ code: 'unknown-variable', id: variable.id, name: refId });
    });
  });

  const state = new Map<string, 'visiting' | 'done'>();
  const depthOf = (id: string): number => {
    const mark = state.get(id);
    if (mark === 'visiting') {
      issues.push({ code: 'cycle', id });
      return DATA_VARIABLE_MAX_DEPTH + 1;
    }
    if (mark === 'done') return depths.get(id) ?? 1;
    state.set(id, 'visiting');
    const variable = byId.get(id);
    const upstream = variable ? directDependencies(variable) : [];
    const depth = upstream.length === 0
      ? 1
      : 1 + Math.max(...upstream.map((refId) => (byId.has(refId) ? depthOf(refId) : 1)));
    depths.set(id, depth);
    state.set(id, 'done');
    if (depth > DATA_VARIABLE_MAX_DEPTH) issues.push({ code: 'too-deep', id });
    return depth;
  };
  const depths = new Map<string, number>();
  variables.forEach((variable) => depthOf(variable.id));
  return issues;
};

export const executionOrder = (variables: DataVariable[], roots: readonly string[]): string[] => {
  const byId = new Map(variables.map((variable) => [variable.id, variable]));
  const needed = new Set<string>();
  const visit = (id: string) => {
    if (!byId.has(id) || needed.has(id)) return;
    needed.add(id);
    directDependencies(byId.get(id)!).forEach(visit);
  };
  roots.forEach(visit);
  const ordered: string[] = [];
  const seen = new Set<string>();
  const walk = (id: string, stack: Set<string>) => {
    if (seen.has(id) || stack.has(id) || !needed.has(id)) return;
    stack.add(id);
    directDependencies(byId.get(id)!).forEach((refId) => walk(refId, stack));
    stack.delete(id);
    seen.add(id);
    ordered.push(id);
  };
  [...needed].forEach((id) => walk(id, new Set()));
  return ordered;
};

const rowListOf = (payload: unknown): unknown[] | null => {
  if (Array.isArray(payload)) return payload;
  if (isRecord(payload) && Array.isArray(payload.items)) return payload.items;
  return null;
};

/** 一层字符串数组摊进取值列。元素不是字符串时返回 null，调用方整列失败。 */
const stringItems = (cell: unknown[]): string[] | null => {
  const items: string[] = [];
  for (const item of cell) {
    if (isEmptyParamValue(item)) continue;
    if (typeof item !== 'string') return null;
    items.push(item);
  }
  return items;
};

export const extractValueColumn = (payload: unknown, field: string): ColumnResult => {
  const rows = rowListOf(payload);
  if (!rows) return { status: 'blocked', reason: 'shape' };
  if (rows.length > DATA_VARIABLE_ROW_LIMIT) return { status: 'blocked', reason: 'too-many' };
  if (rows.length === 0) return { status: 'blocked', reason: 'nodata' };
  const values: unknown[] = [];
  let sawField = false;
  for (const row of rows) {
    if (!isRecord(row) || !Object.prototype.hasOwnProperty.call(row, field)) continue;
    sawField = true;
    const cell = row[field];
    if (isEmptyParamValue(cell)) continue;
    if (Array.isArray(cell)) {
      const items = stringItems(cell);
      if (!items) return { status: 'blocked', reason: 'cell' };
      values.push(...items);
      continue;
    }
    values.push(cell);
  }
  if (!sawField) return { status: 'blocked', reason: 'missing-field' };
  if (values.length === 0) return { status: 'blocked', reason: 'nodata' };
  return { status: 'ready', values };
};

export type ResolvedParam =
  | { blocked: true; reason: ColumnBlockReason }
  | { blocked: false; value: unknown };

const readyParam = (
  result: ResolvedParam,
): { blocked: false; value: unknown } | null => (
  result.blocked ? null : result as { blocked: false; value: unknown }
);

const readyRecord = (
  result: { blocked: true; reason: ColumnBlockReason } | { blocked: false; params: Record<string, unknown> },
): { blocked: false; params: Record<string, unknown> } | null => (
  result.blocked ? null : result as { blocked: false; params: Record<string, unknown> }
);

/** 选项查询读到数据变量时换成取值列。列还没好就当没有值，请求里不能留下编号。 */
export const substituteDataVariableUpstream = (
  value: unknown,
  columns: Record<string, ColumnResult> | undefined,
): unknown => {
  if (!isDataVariableRef(value)) return value;
  const column = columns?.[value.dataVariableId];
  if (!column || column.status !== 'ready') return undefined;
  return column.values;
};

export const resolveParamValue = (
  value: unknown,
  columns: Record<string, ColumnResult>,
): ResolvedParam => {
  if (isDataVariableRef(value)) {
    const column = columns[value.dataVariableId];
    if (!column) return { blocked: true, reason: 'upstream' };
    if (column.status !== 'ready') return { blocked: true, reason: column.reason };
    return { blocked: false, value: column.values };
  }
  if (isConditionGroup(value)) {
    const items = [];
    for (const item of value.items) {
      if (!isRecord(item)) {
        items.push(item);
        continue;
      }
      const resolved = resolveParamValue(item.value, columns);
      const ready = readyParam(resolved);
      if (!ready) return resolved;
      items.push({ ...item, value: ready.value });
    }
    return { blocked: false, value: { ...value, items } };
  }
  return { blocked: false, value };
};

export const resolveParamRecord = (
  params: Record<string, unknown>,
  columns: Record<string, ColumnResult>,
): { blocked: true; reason: ColumnBlockReason } | { blocked: false; params: Record<string, unknown> } => {
  const next: Record<string, unknown> = {};
  for (const [name, value] of Object.entries(params)) {
    const resolved = resolveParamValue(value, columns);
    const ready = readyParam(resolved);
    if (!ready) {
      return { blocked: true, reason: (resolved as { reason: ColumnBlockReason }).reason };
    }
    if (isEmptyParamValue(ready.value)) continue;
    next[name] = ready.value;
  }
  return { blocked: false, params: next };
};

export interface VariableRun {
  columns: Record<string, ColumnResult>;
  payloads: Record<string, unknown>;
}

export const columnBlockReasonKey = (reason: ColumnBlockReason): string => {
  if (reason === 'nodata') return 'dataVariable.reasonNoData';
  if (reason === 'empty') return 'dataVariable.reasonEmpty';
  if (reason === 'shape') return 'dataVariable.reasonShape';
  if (reason === 'cell') return 'dataVariable.reasonCell';
  if (reason === 'missing-field') return 'dataVariable.reasonMissingField';
  if (reason === 'too-many') return 'dataVariable.reasonTooMany';
  if (reason === 'upstream') return 'dataVariable.reasonUpstream';
  return 'dataVariable.reasonRequest';
};

export const runDataVariables = async ({
  variables,
  roots,
  fetchRows,
  reuse,
  refreshIds,
}: {
  variables: DataVariable[];
  roots: readonly string[];
  fetchRows: (variable: DataVariable, params: Record<string, unknown>) => Promise<unknown>;
  /** 这次不用重查的列。 */
  reuse?: Record<string, ColumnResult>;
  /** 只重查这些编号。缺省时根上的每条都查。 */
  refreshIds?: ReadonlySet<string>;
}): Promise<VariableRun> => {
  const byId = new Map(variables.map((variable) => [variable.id, variable]));
  const columns: Record<string, ColumnResult> = {};
  const payloads: Record<string, unknown> = {};
  for (const id of executionOrder(variables, roots)) {
    const variable = byId.get(id);
    if (!variable) continue;
    if (refreshIds && !refreshIds.has(id)) {
      const kept = reuse?.[id];
      if (kept) columns[id] = kept;
      continue;
    }
    const resolved = resolveParamRecord(variable.params, columns);
    const ready = readyRecord(resolved);
    if (!ready) {
      columns[id] = {
        status: 'blocked',
        reason: (resolved as { reason: ColumnBlockReason }).reason,
      };
      continue;
    }
    try {
      const payload = await fetchRows(variable, ready.params);
      payloads[id] = payload;
      columns[id] = extractValueColumn(payload, variable.valueField);
    } catch (error) {
      columns[id] = {
        status: 'blocked',
        reason: error instanceof DataVariableBlocked ? error.reason : 'request',
      };
    }
  }
  return { columns, payloads };
};
