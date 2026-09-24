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
}

export interface DataReferenceEdge {
  source: string;
  target: string;
}

const DEFAULT_REFERENCE_LABELS: DataReferenceLabels = {
  triggerInput: '触发输入',
  systemContext: '系统上下文',
  allOutputs: '全部输出',
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

function collectEdgeAncestors(currentReference: string, edges: DataReferenceEdge[], taskReferences: Set<string>): Set<string> {
  const incoming = new Map<string, string[]>();
  for (const edge of edges) incoming.set(edge.target, [...(incoming.get(edge.target) || []), edge.source]);
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

function schemaOptions(
  schema: JsonSchema | undefined,
  source: string,
  expressionPrefix: string,
  sourceKind: DataReferenceSourceKind,
  sourceReference: string,
  sensitive = false,
  parentPath = '',
): DataReferenceOption[] {
  return Object.entries(schema?.properties || {}).flatMap(([field, fieldSchema]) => {
    const path = parentPath ? `${parentPath}.${field}` : field;
    const option: DataReferenceOption = {
      label: `${source} · ${path} (${normalizedType(fieldSchema) || 'unknown'})`,
      value: `${expressionPrefix}${path}}`,
      type: normalizedType(fieldSchema),
      source,
      sourceKind,
      sourceReference,
      path,
      nullable: isNullable(fieldSchema),
      sensitive: sensitive || Boolean(fieldSchema.sensitive),
      widget: fieldSchema['x-widget'],
    };
    if (normalizedType(fieldSchema) !== 'object') return [option];
    return [option, ...schemaOptions(fieldSchema, source, expressionPrefix, sourceKind, sourceReference, option.sensitive, path)];
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

function systemContextOptions(systemContextLabel: string): DataReferenceOption[] {
  return SYSTEM_CONTEXT.map((field) => ({
    label: `${systemContextLabel} · ${field.key} (${field.type})`,
    value: `\${system.${field.key}}`,
    type: field.type,
    source: systemContextLabel,
    sourceKind: 'system' as const,
    sourceReference: 'system',
    path: field.key,
  }));
}

export function buildDataReferenceOptions(
  definition: ConductorDefinition,
  currentReference: string,
  atoms: AtomCatalogItem[],
  workflowInputSchema: JsonSchema,
  labels: DataReferenceLabels = DEFAULT_REFERENCE_LABELS,
  edges?: DataReferenceEdge[],
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
  const options = schemaOptions(workflowInputSchema, labels.triggerInput, '${workflow.input.', 'trigger', 'workflow.input');
  for (const reference of reachable) {
    const task = taskByReference.get(reference);
    const schema = task ? atomByKey.get(task.name)?.output_schema : undefined;
    if (schema) {
      options.push({
        label: `${reference} · ${labels.allOutputs} (${normalizedType(schema) || 'object'})`,
        value: `\${${reference}.output}`,
        type: normalizedType(schema) || 'object',
        source: reference,
        sourceKind: 'node_output',
        sourceReference: reference,
        path: '',
      });
    }
    options.push(...schemaOptions(schema, reference, `\${${reference}.output.`, 'node_output', reference));
  }
  options.push(...systemContextOptions(labels.systemContext));
  return options;
}

export function buildWorkflowOutputReferenceOptions(
  definition: ConductorDefinition,
  atoms: AtomCatalogItem[],
  labels: Pick<DataReferenceLabels, 'allOutputs'> = DEFAULT_REFERENCE_LABELS,
): DataReferenceOption[] {
  const atomByKey = new Map(atoms.map((atom) => [atom.key, atom]));
  return definition.tasks.flatMap((task) => {
    const schema = atomByKey.get(task.name)?.output_schema;
    if (!schema) return [];
    return [
      {
        label: `${task.taskReferenceName} · ${labels.allOutputs} (${normalizedType(schema) || 'object'})`,
        value: `\${${task.taskReferenceName}.output}`,
        type: normalizedType(schema) || 'object',
        source: task.taskReferenceName,
        sourceKind: 'node_output' as const,
        sourceReference: task.taskReferenceName,
        path: '',
      },
      ...schemaOptions(
        schema,
        task.taskReferenceName,
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
  return { compatible: false, reason: `来源类型 ${reference.type} 不能绑定到 ${targetType}` };
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
