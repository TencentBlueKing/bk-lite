import type { Edge, Node } from '@xyflow/react';

import type { ConductorDefinition, ConductorTask, JsonSchema, WorkflowTriggerType } from './types';
import type { ConditionConfiguration } from './condition-dsl';
import { approvalDecisionPairs } from './approval-dsl';

export const START_NODE_ID = '__legacy_start__';

export interface WorkflowTriggerNode {
  id: string;
  name: string;
  trigger_type: WorkflowTriggerType;
  input_schema: JsonSchema;
  config: Record<string, unknown>;
}

export interface WorkflowReturnNode {
  id: string;
  name: string;
  return_type: 'WEBHOOK';
  config: Record<string, unknown>;
}

export interface WorkflowCanvasMetadata extends Record<string, unknown> {
  positions?: Record<string, { x: number; y: number }>;
  node_titles?: Record<string, string>;
  edges?: Edge[];
  trigger_nodes?: WorkflowTriggerNode[];
  return_nodes?: WorkflowReturnNode[];
  condition_nodes?: Record<string, ConditionConfiguration>;
  node_test_data?: Record<string, unknown>;
}

export interface WorkflowCanvasNodeData extends Record<string, unknown> {
  title: string;
  meta: string;
  kind: 'trigger' | 'atom' | 'control' | 'return';
  taskType?: ConductorTask['type'];
  atomKey?: string;
  atomCategory?: string;
  triggerType?: WorkflowTriggerType;
  returnType?: WorkflowReturnNode['return_type'];
  branches?: Array<{ id: string; label: string }>;
}

function approvalBranchLabel(id: string): string {
  if (id === 'true') return '通过';
  if (id === 'false') return '驳回';
  if (id === 'timeout') return '超时';
  return id;
}

/** MVP 条件节点是布尔 SWITCH：多条规则合成 true/false，不是多路 case。 */
function conditionBranchLabel(id: string): string {
  if (id === 'true') return '满足';
  if (id === 'false') return '不满足';
  return id;
}

export function projectApprovalCanvasEdges(definition: ConductorDefinition, edges: Edge[]): Edge[] {
  const pairs = approvalDecisionPairs(definition.tasks);
  const approvalByDecision = new Map(pairs.map(({ approval, decision }) => [decision.taskReferenceName, approval.taskReferenceName]));
  const internalEdges = new Set(pairs.map(({ approval, decision }) => `${approval.taskReferenceName}\u0000${decision.taskReferenceName}`));
  return edges.flatMap((edge) => {
    if (internalEdges.has(`${edge.source}\u0000${edge.target}`)) return [];
    const approvalReference = approvalByDecision.get(edge.source);
    return [{ ...edge, ...(approvalReference ? { source: approvalReference } : {}) }];
  });
}

export function expandApprovalCanvasEdges(definition: ConductorDefinition, edges: Edge[]): Edge[] {
  const pairs = approvalDecisionPairs(definition.tasks);
  const pairByApproval = new Map(pairs.map((pair) => [pair.approval.taskReferenceName, pair]));
  const projected = projectApprovalCanvasEdges(definition, edges);
  const expanded = projected.map((edge) => {
    const pair = pairByApproval.get(edge.source);
    if (!pair || !edge.sourceHandle || !(edge.sourceHandle in (pair.decision.decisionCases || {}))) return edge;
    return { ...edge, source: pair.decision.taskReferenceName };
  });
  for (const { approval, decision } of pairs) {
    expanded.push({
      id: `${approval.taskReferenceName}-${decision.taskReferenceName}`,
      source: approval.taskReferenceName,
      target: decision.taskReferenceName,
    });
  }
  return expanded;
}

export function flattenTasks(tasks: ConductorTask[]): ConductorTask[] {
  return tasks.flatMap((task) => [
    task,
    ...(task.forkTasks || []).flatMap(flattenTasks),
    ...Object.values(task.decisionCases || {}).flatMap(flattenTasks),
    ...flattenTasks(task.defaultCase || []),
  ]);
}

function generatedTaskPairs(tasks: ConductorTask[]): Array<[string, string]> {
  return tasks.flatMap((task, index) => {
    const next = tasks[index + 1];
    const pairs: Array<[string, string]> = next ? [[task.taskReferenceName, next.taskReferenceName]] : [];
    const branches = [
      ...(task.forkTasks || []),
      ...Object.values(task.decisionCases || {}),
      ...(task.defaultCase?.length ? [task.defaultCase] : []),
    ];
    for (const branch of branches) {
      if (branch.length) pairs.push([task.taskReferenceName, branch[0].taskReferenceName], ...generatedTaskPairs(branch));
      if (branch.length && next?.type === 'JOIN') pairs.push([branch.at(-1)!.taskReferenceName, next.taskReferenceName]);
    }
    return pairs;
  });
}

export function workflowTriggerNodes(metadata: WorkflowCanvasMetadata): WorkflowTriggerNode[] {
  if (metadata.trigger_nodes !== undefined) return metadata.trigger_nodes;
  return [{
    id: 'trigger_form', name: '表单触发器', trigger_type: 'FORM',
    input_schema: (metadata.input_schema || { type: 'object', properties: {}, required: [] }) as JsonSchema,
    config: {},
  }];
}

function schemaFromSample(value: unknown, title: string): JsonSchema {
  if (Array.isArray(value)) {
    return {
      type: 'array',
      title,
      ...(value.length ? { items: schemaFromSample(value[0], title) } : {}),
    };
  }
  if (value !== null && typeof value === 'object') {
    return {
      type: 'object',
      title,
      properties: Object.fromEntries(
        Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, schemaFromSample(item, key)]),
      ),
      additionalProperties: true,
    };
  }
  return { type: value === null ? 'null' : typeof value === 'number' && Number.isInteger(value) ? 'integer' : typeof value, title };
}

function enrichSchemaFromSample(schema: JsonSchema, sample: unknown): JsonSchema {
  if (sample === null || typeof sample !== 'object' || Array.isArray(sample)) return schema;
  const sampleObject = sample as Record<string, unknown>;
  const properties = Object.fromEntries(Object.entries(schema.properties || {}).map(([key, field]) => {
    if (!Object.hasOwn(sampleObject, key)) return [key, field];
    const inferred = schemaFromSample(sampleObject[key], field.title || key);
    if (field.type === 'object' && inferred.type === 'object') {
      return [key, { ...field, properties: { ...(field.properties || {}), ...(inferred.properties || {}) } }];
    }
    return [key, field];
  }));
  return { ...schema, properties };
}

/** Return the input fields guaranteed by every trigger path. */
export function commonTriggerInputSchema(metadata: WorkflowCanvasMetadata): JsonSchema {
  const triggers = workflowTriggerNodes(metadata);
  if (!triggers.length) return { type: 'object', properties: {}, required: [], additionalProperties: false };
  const schemas = triggers.map((trigger) => enrichSchemaFromSample(
    trigger.input_schema || {},
    metadata.node_test_data?.[trigger.id],
  ));
  const firstProperties = schemas[0].properties || {};
  const properties = Object.fromEntries(Object.entries(firstProperties).filter(([key, field]) => (
    schemas.every((schema) => JSON.stringify(schema.properties?.[key]) === JSON.stringify(field))
  )));
  const required = Object.keys(properties).filter((key) => schemas.every((schema) => schema.required?.includes(key)));
  return { type: 'object', properties, required, additionalProperties: false };
}

export function buildWorkflowFlow(
  definition: ConductorDefinition,
  metadata: WorkflowCanvasMetadata = {},
  atomLabels: Record<string, string> = {},
  atomCategories: Record<string, string> = {},
): { nodes: Array<Node<WorkflowCanvasNodeData>>; edges: Edge[] } {
  const triggers = workflowTriggerNodes(metadata);
  const returns = metadata.return_nodes || [];
  const approvalPairs = approvalDecisionPairs(definition.tasks);
  const approvalPairByReference = new Map(approvalPairs.map((pair) => [pair.approval.taskReferenceName, pair]));
  const hiddenApprovalDecisions = new Set(approvalPairs.map(({ decision }) => decision.taskReferenceName));
  const tasks = flattenTasks(definition.tasks).filter((task) => (
    !task.taskReferenceName.startsWith('__auto_') && !hiddenApprovalDecisions.has(task.taskReferenceName)
  ));
  const nodes: Array<Node<WorkflowCanvasNodeData>> = [
    ...triggers.map((trigger, index) => ({
      id: trigger.id, type: 'workflowCanvas',
      position: metadata.positions?.[trigger.id] || { x: 20, y: 160 + index * 180 },
      data: { title: trigger.name, meta: trigger.trigger_type, kind: 'trigger' as const, triggerType: trigger.trigger_type },
    })),
    ...tasks.map((task, index) => ({
      id: task.taskReferenceName, type: 'workflowCanvas',
      position: metadata.positions?.[task.taskReferenceName] || { x: 260 + index * 220, y: 260 },
      data: {
        title: metadata.node_titles?.[task.taskReferenceName] || atomLabels[task.name] || task.name,
        meta: task.type === 'SIMPLE' ? task.name : task.type,
        kind: task.type === 'SIMPLE' ? 'atom' as const : 'control' as const,
        taskType: task.type,
        atomKey: task.type === 'SIMPLE' ? task.name : undefined,
        atomCategory: task.type === 'SIMPLE' ? atomCategories[task.name] : undefined,
        branches: task.type === 'HUMAN'
          ? Object.keys(approvalPairByReference.get(task.taskReferenceName)?.decision.decisionCases || {}).map((id) => ({ id, label: approvalBranchLabel(id) }))
          : task.type === 'SWITCH'
            ? Object.keys(task.decisionCases || {}).map((id) => ({ id, label: conditionBranchLabel(id) }))
            : undefined,
      },
    })),
    ...returns.map((item, index) => ({
      id: item.id, type: 'workflowCanvas',
      position: metadata.positions?.[item.id] || { x: 1650, y: 160 + index * 180 },
      data: { title: item.name, meta: `${item.return_type} Return`, kind: 'return' as const, returnType: item.return_type },
    })),
  ];
  const nodeIds = new Set(nodes.map((node) => node.id));
  const persisted = projectApprovalCanvasEdges(definition, metadata.edges || []).filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));
  if (persisted.length) return { nodes, edges: persisted };
  const taskEdges = projectApprovalCanvasEdges(definition, generatedTaskPairs(definition.tasks).map(([source, target]) => ({ id: `${source}-${target}`, source, target })));
  const first = definition.tasks[0]?.taskReferenceName;
  const rawLast = definition.tasks.at(-1)?.taskReferenceName;
  const last = approvalPairs.find(({ decision }) => decision.taskReferenceName === rawLast)?.approval.taskReferenceName || rawLast;
  return {
    nodes,
    edges: [
      ...(first ? triggers.map((item) => ({ id: `${item.id}-${first}`, source: item.id, target: first })) : []),
      ...taskEdges,
      ...(last ? returns.map((item) => ({ id: `${last}-${item.id}`, source: last, target: item.id })) : []),
    ],
  };
}
