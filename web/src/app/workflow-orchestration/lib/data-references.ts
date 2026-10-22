import type {
  AtomCatalogItem,
  ConductorDefinition,
  ConductorTask,
  JsonSchema,
  NodeInputBinding,
} from './types';

export type DataReferenceSourceKind = 'trigger' | 'system' | 'node_output';

export interface DataReferenceOption {
  label: string;
  value: string;
  type?: string;
  source: string;
  sourceLabel?: string;
  displayName?: string;
  jsonPath?: string;
  sourceKind?: DataReferenceSourceKind;
  sourceReference?: string;
  path?: string;
  nullable?: boolean;
  sensitive?: boolean;
  widget?: JsonSchema['x-widget'];
}

export interface BindingCompatibility {
  compatible: boolean;
  reason?: string;
}

export interface DataReferenceLabels {
  triggerInput: string;
  systemContext: string;
  allOutputs: string;
  systemFields?: Record<string, string>;
}

export interface DataReferenceEdge {
  source: string;
  target: string;
}

const DEFAULT_REFERENCE_LABELS: DataReferenceLabels = {
  triggerInput: '触发输入',
  systemContext: '运行信息',
  allOutputs: '全部输出',
  systemFields: {
    execution_id: '执行号',
    workflow_id: '流程',
    workflow_version: '流程版本',
    organization_id: '组织',
    trigger_id: '触发器',
    trigger_type: '触发类型',
    actor_id: '发起人标识',
    actor_name: '发起人',
    started_at: '开始时间',
    trace_id: '追踪号',
  },
};

const FULL_REFERENCE_PATTERN = /^\$\{[^{}]+}$/;
const ANY_REFERENCE_PATTERN = /\$\{[^{}]+}/;

export const normalizedType = (schema?: JsonSchema) => {
  const value = schema?.type;
  return Array.isArray(value) ? value.find((item) => item !== 'null') : value;
};

const isNullable = (schema?: JsonSchema) => Array.isArray(schema?.type) && schema.type.includes('null');

function collectReachability(tasks: ConductorTask[], inherited: string[], result: Map<string, string[]>) {
  const reachable = [...inherited];
  for (const task of tasks) {
    if (task.type === 'JOIN') {
      for (const joinedReference of task.joinOn || []) {
        for (const dependency of [...(result.get(joinedReference) || []), joinedReference]) {
          if (!reachable.includes(dependency)) reachable.push(dependency);
        }
      }
    }
    result.set(task.taskReferenceName, [...reachable]);
    const nestedInherited = [...reachable, task.taskReferenceName];
    for (const branch of task.forkTasks || []) collectReachability(branch, nestedInherited, result);
    for (const branch of Object.values(task.decisionCases || {})) collectReachability(branch, nestedInherited, result);
    if (task.defaultCase?.length) collectReachability(task.defaultCase, nestedInherited, result);
    // Branch descendants are promoted only by an explicit JOIN.joinOn declaration.
    reachable.push(task.taskReferenceName);
  }
}

function collectTasks(tasks: ConductorTask[], result: Map<string, ConductorTask>) {
  for (const task of tasks) {
    result.set(task.taskReferenceName, task);
    for (const branch of task.forkTasks || []) collectTasks(branch, result);
    for (const branch of Object.values(task.decisionCases || {})) collectTasks(branch, result);
    collectTasks(task.defaultCase || [], result);
  }
}

function incomingEdges(edges: DataReferenceEdge[]): Map<string, string[]> {
  const incoming = new Map<string, string[]>();
  for (const edge of edges) incoming.set(edge.target, [...(incoming.get(edge.target) || []), edge.source]);
  return incoming;
}

function collectEdgeAncestors(currentReference: string, edges: DataReferenceEdge[], taskReferences: Set<string>): Set<string> {
  const incoming = incomingEdges(edges);
  const ancestors = new Set<string>();
  const pending = [...(incoming.get(currentReference) || [])];
  while (pending.length) {
    const reference = pending.pop()!;
    if (ancestors.has(reference)) continue;
    ancestors.add(reference);
    pending.push(...(incoming.get(reference) || []));
  }
  return new Set([...ancestors].filter((reference) => taskReferences.has(reference)));
}

function reachesCanvasTrigger(currentReference: string, edges: DataReferenceEdge[], taskReferences: Set<string>): boolean {
  const incoming = incomingEdges(edges);
  const pending = [currentReference];
  const seen = new Set<string>();
  while (pending.length) {
    const reference = pending.pop()!;
    if (seen.has(reference)) continue;
    seen.add(reference);
    for (const source of incoming.get(reference) || []) {
      if (!taskReferences.has(source)) return true;
      pending.push(source);
    }
  }
  return false;
}

function definitionOrder(tasks: ConductorTask[]): Map<string, number> {
  const order = new Map<string, number>();
  const visit = (items: ConductorTask[]) => {
    items.forEach((task) => {
      if (!order.has(task.taskReferenceName)) order.set(task.taskReferenceName, order.size);
      (task.forkTasks || []).forEach(visit);
      Object.values(task.decisionCases || {}).forEach(visit);
      visit(task.defaultCase || []);
    });
  };
  visit(tasks);
  return order;
}

function schemaOptions(
  schema: JsonSchema | undefined,
  source: string,
  sourceLabel: string,
  expressionPrefix: string,
  sourceKind: DataReferenceSourceKind,
  sourceReference: string,
  sensitive = false,
  parentPath = '',
): DataReferenceOption[] {
  return Object.entries(schema?.properties || {}).flatMap(([field, fieldSchema]) => {
    const path = parentPath ? `${parentPath}.${field}` : field;
    const displayName = fieldSchema.title || path;
    const option: DataReferenceOption = {
      label: `${sourceLabel} · ${displayName}`,
      value: `${expressionPrefix}${path}}`,
      type: normalizedType(fieldSchema),
      source,
      sourceLabel,
      displayName,
      jsonPath: path,
      sourceKind,
      sourceReference,
      path,
      nullable: isNullable(fieldSchema),
      sensitive: sensitive || Boolean(fieldSchema.sensitive),
      widget: fieldSchema['x-widget'],
    };
    if (normalizedType(fieldSchema) !== 'object') return [option];
    return [option, ...schemaOptions(fieldSchema, source, sourceLabel, expressionPrefix, sourceKind, sourceReference, option.sensitive, path)];
  });
}

const SYSTEM_CONTEXT: Array<{ key: string; type: string }> = [
  { key: 'execution_id', type: 'string' },
  { key: 'workflow_id', type: 'string' },
  { key: 'workflow_version', type: 'integer' },
  { key: 'organization_id', type: 'string' },
  { key: 'trigger_id', type: 'string' },
  { key: 'trigger_type', type: 'string' },
  { key: 'actor_id', type: 'string' },
  { key: 'actor_name', type: 'string' },
  { key: 'started_at', type: 'string' },
  { key: 'trace_id', type: 'string' },
];

function systemContextOptions(labels: DataReferenceLabels): DataReferenceOption[] {
  return SYSTEM_CONTEXT.map((field) => {
    const displayName = labels.systemFields?.[field.key] || field.key;
    return {
      label: `${labels.systemContext} · ${displayName}`,
      value: `\${system.${field.key}}`,
      type: field.type,
      source: labels.systemContext,
      sourceLabel: labels.systemContext,
      displayName,
      jsonPath: field.key,
      sourceKind: 'system' as const,
      sourceReference: 'system',
      path: field.key,
    };
  });
}

export function resolveTriggerGroupLabel(
  currentReference: string,
  triggers: Array<{ id: string; name: string }>,
  edges: DataReferenceEdge[] | undefined,
  fallback: string,
): string {
  const named = triggers.flatMap((item) => {
    const name = item.name.trim();
    return name ? [{ id: item.id, name }] : [];
  });
  if (!named.length) return fallback;
  const onlyName = new Set(named.map((item) => item.name));
  if (!edges?.length) return onlyName.size === 1 ? named[0].name : fallback;

  const triggerIds = new Set(named.map((item) => item.id));
  const incoming = new Map<string, string[]>();
  edges.forEach((edge) => incoming.set(edge.target, [...(incoming.get(edge.target) || []), edge.source]));
  const found = new Set<string>();
  const pending = [currentReference];
  const seen = new Set<string>();
  while (pending.length) {
    const reference = pending.pop()!;
    if (seen.has(reference)) continue;
    seen.add(reference);
    (incoming.get(reference) || []).forEach((source) => {
      if (triggerIds.has(source)) found.add(source);
      else pending.push(source);
    });
  }
  const names = [...new Set([...found].map((id) => named.find((item) => item.id === id)?.name).filter((item): item is string => Boolean(item)))];
  if (names.length === 1) return names[0];
  if (!names.length && onlyName.size === 1) return named[0].name;
  return fallback;
}

export function buildDataReferenceOptions(
  definition: ConductorDefinition,
  currentReference: string,
  atoms: AtomCatalogItem[],
  workflowInputSchema: JsonSchema,
  labels: DataReferenceLabels = DEFAULT_REFERENCE_LABELS,
  edges?: DataReferenceEdge[],
  nodeTitles?: Record<string, string>,
  triggerSourceLabel?: string,
): DataReferenceOption[] {
  const taskByReference = new Map<string, ConductorTask>();
  collectTasks(definition.tasks, taskByReference);
  let reachable: Set<string>;
  if (edges) {
    reachable = collectEdgeAncestors(currentReference, edges, new Set(taskByReference.keys()));
  } else {
    const reachability = new Map<string, string[]>();
    collectReachability(definition.tasks, [], reachability);
    reachable = new Set(reachability.get(currentReference) || []);
  }
  const atomByKey = new Map(atoms.map((atom) => [atom.key, atom]));
  const order = definitionOrder(definition.tasks);
  const sorted = [...reachable].sort((left, right) => (order.get(left) ?? 0) - (order.get(right) ?? 0));
  const baseLabels = sorted.map((reference) => {
    const task = taskByReference.get(reference);
    const atomName = task ? atomByKey.get(task.name)?.name : undefined;
    return { reference, base: nodeTitles?.[reference] || atomName || reference };
  });
  const labelCounts = new Map<string, number>();
  baseLabels.forEach(({ base }) => labelCounts.set(base, (labelCounts.get(base) || 0) + 1));
  const showTriggerInput = !edges || reachesCanvasTrigger(currentReference, edges, new Set(taskByReference.keys()));
  const triggerBase = triggerSourceLabel?.trim() || labels.triggerInput;
  const hasTriggerFields = showTriggerInput && Object.keys(workflowInputSchema.properties || {}).length > 0;
  if (hasTriggerFields) labelCounts.set(triggerBase, (labelCounts.get(triggerBase) || 0) + 1);
  const triggerLabel = hasTriggerFields && (labelCounts.get(triggerBase) || 0) > 1 ? `${triggerBase} · workflow.input` : triggerBase;
  const options = hasTriggerFields
    ? schemaOptions(workflowInputSchema, triggerLabel, triggerLabel, '${workflow.input.', 'trigger', 'workflow.input')
    : [];
  baseLabels.forEach(({ reference, base }) => {
    const sourceLabel = (labelCounts.get(base) || 0) > 1 ? `${base} · ${reference}` : base;
    const task = taskByReference.get(reference);
    const schema = task ? atomByKey.get(task.name)?.output_schema : undefined;
    if (schema) {
      options.push({
        label: `${sourceLabel} · ${labels.allOutputs}`,
        value: `\${${reference}.output}`,
        type: normalizedType(schema) || 'object',
        source: reference,
        sourceLabel,
        displayName: labels.allOutputs,
        jsonPath: 'output',
        sourceKind: 'node_output',
        sourceReference: reference,
        path: '',
      });
    }
    options.push(...schemaOptions(schema, reference, sourceLabel, `\${${reference}.output.`, 'node_output', reference));
  });
  options.push(...systemContextOptions(labels));
  return options;
}

export function buildWorkflowOutputReferenceOptions(
  definition: ConductorDefinition,
  atoms: AtomCatalogItem[],
  labels: Pick<DataReferenceLabels, 'allOutputs'> = DEFAULT_REFERENCE_LABELS,
  nodeTitles?: Record<string, string>,
): DataReferenceOption[] {
  const atomByKey = new Map(atoms.map((atom) => [atom.key, atom]));
  return definition.tasks.flatMap((task) => {
    const schema = atomByKey.get(task.name)?.output_schema;
    if (!schema) return [];
    const sourceLabel = nodeTitles?.[task.taskReferenceName] || atomByKey.get(task.name)?.name || task.taskReferenceName;
    return [
      {
        label: `${sourceLabel} · ${labels.allOutputs}`,
        value: `\${${task.taskReferenceName}.output}`,
        type: normalizedType(schema) || 'object',
        source: task.taskReferenceName,
        sourceLabel,
        displayName: labels.allOutputs,
        jsonPath: 'output',
        sourceKind: 'node_output' as const,
        sourceReference: task.taskReferenceName,
        path: '',
      },
      ...schemaOptions(
        schema,
        task.taskReferenceName,
        sourceLabel,
        `\${${task.taskReferenceName}.output.`,
        'node_output',
        task.taskReferenceName,
      ),
    ];
  });
}

export function dataReferenceCompatibility(reference: DataReferenceOption, targetSchema: JsonSchema): BindingCompatibility {
  const targetType = normalizedType(targetSchema);
  if (!targetType) return { compatible: true };
  if (!reference.type) return { compatible: false, reason: '来源没有声明类型，不能执行严格类型校验' };
  if (reference.sensitive && !targetSchema.secretCompatible) return { compatible: false, reason: '目标字段未声明可接收敏感值' };
  if (reference.type === targetType) return { compatible: true };
  if (reference.type === 'integer' && targetType === 'number') return { compatible: true };
  if (targetType === 'string') {
    // 宽收：标题/通知正文等；默认仅 string（URL、query、content 等）
    if (targetSchema['x-text-surface'] === 'coerce') return { compatible: true };
    return { compatible: false, reason: `来源类型 ${reference.type} 不能绑定到 string` };
  }
  return { compatible: false, reason: `来源类型 ${reference.type} 不能绑定到 ${targetType}` };
}

export function coerceResolvedValueForSchema(value: unknown, targetSchema: JsonSchema | undefined): unknown {
  if (!targetSchema || normalizedType(targetSchema) !== 'string') return value;
  if (value == null || typeof value === 'string') return value;
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function coerceResolvedInputsForSchema(
  inputs: Record<string, unknown>,
  schema: JsonSchema | undefined,
): Record<string, unknown> {
  const properties = schema?.properties || {};
  return Object.fromEntries(Object.entries(inputs).map(([key, value]) => (
    [key, coerceResolvedValueForSchema(value, properties[key])]
  )));
}

export function compatibleDataReferences(references: DataReferenceOption[], targetSchema: JsonSchema): DataReferenceOption[] {
  return references.filter((reference) => dataReferenceCompatibility(reference, targetSchema).compatible);
}

export function parseNodeInputBinding(value: unknown): NodeInputBinding {
  if (typeof value === 'string' && FULL_REFERENCE_PATTERN.test(value)) return { kind: 'reference', expression: value };
  if (typeof value === 'string' && ANY_REFERENCE_PATTERN.test(value)) return { kind: 'template', template: value };
  return { kind: 'literal', value };
}

export function compileNodeInputBinding(binding: NodeInputBinding): unknown {
  if (binding.kind === 'literal') return binding.value;
  if (binding.kind === 'reference') return binding.expression;
  return binding.template;
}

function valueAtPath(value: unknown, path = ''): unknown {
  if (!path) return value;
  return path.split('.').reduce<unknown>((current, segment) => {
    if (current == null || typeof current !== 'object') return undefined;
    return (current as Record<string, unknown>)[segment];
  }, value);
}

export function dataReferencePreview(
  reference: DataReferenceOption,
  workflowInputs: Record<string, unknown>,
  nodeOutputs: Record<string, unknown>,
): unknown {
  if (reference.sourceKind === 'trigger') return valueAtPath(workflowInputs, reference.path);
  if (reference.sourceKind === 'node_output' && reference.sourceReference) return valueAtPath(nodeOutputs[reference.sourceReference], reference.path);
  return undefined;
}

const EXACT_REFERENCE = /^\$\{([^{}]+)}$/;
const EMBEDDED_REFERENCE = /\$\{([^{}]+)}/g;
const RUNTIME_WORKFLOW_INPUTS = new Set(['team', 'actor', 'execution_id']);

function resolveExpression(
  expression: string,
  workflowInputs: Record<string, unknown>,
  nodeOutputs: Record<string, unknown>,
): { found: boolean; value?: unknown } {
  if (expression.startsWith('system.')) return { found: true, value: `\${${expression}}` };
  if (expression.startsWith('workflow.input.')) {
    const path = expression.slice('workflow.input.'.length);
    const value = valueAtPath(workflowInputs, path);
    if (value !== undefined) return { found: true, value };
    if (RUNTIME_WORKFLOW_INPUTS.has(path)) return { found: true, value: `\${${expression}}` };
    return { found: false };
  }
  if (expression.endsWith('.output')) {
    const source = expression.slice(0, -'.output'.length);
    if (!source || nodeOutputs[source] === undefined) return { found: false };
    return { found: true, value: nodeOutputs[source] };
  }
  const separator = '.output.';
  const index = expression.indexOf(separator);
  if (index <= 0) return { found: false };
  const source = expression.slice(0, index);
  const value = valueAtPath(nodeOutputs[source], expression.slice(index + separator.length));
  return value === undefined ? { found: false } : { found: true, value };
}

export function resolveNodeTestInputs(
  inputs: Record<string, unknown>,
  workflowInputs: Record<string, unknown>,
  nodeOutputs: Record<string, unknown>,
): { value: Record<string, unknown>; unresolved: string[] } {
  const unresolved = new Set<string>();
  const visit = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(visit);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, visit(item)]));
    if (typeof value !== 'string') return value;
    const exact = value.match(EXACT_REFERENCE);
    if (exact) {
      const resolved = resolveExpression(exact[1], workflowInputs, nodeOutputs);
      if (!resolved.found) unresolved.add(value);
      return resolved.found ? resolved.value : value;
    }
    return value.replace(EMBEDDED_REFERENCE, (match, expression: string) => {
      const resolved = resolveExpression(expression, workflowInputs, nodeOutputs);
      if (!resolved.found) {
        unresolved.add(match);
        return match;
      }
      return typeof resolved.value === 'string' ? resolved.value : JSON.stringify(resolved.value);
    });
  };
  return { value: visit(inputs) as Record<string, unknown>, unresolved: [...unresolved] };
}
