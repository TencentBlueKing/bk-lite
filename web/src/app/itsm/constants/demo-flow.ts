import type { ConditionGroup, NodeActionDisplay } from '../types';
import { readNodeActionDisplay } from './node-catalog';

export type TransferScope =
  | { type: 'users'; users: string[] }
  | { type: 'handler_groups'; group_ids: number[] };

export interface DesignNode {
  id: string;
  type: string;
  name: string;
  assignee?: { source: string; value: string[] | string | number };
  multi?: { mode: string };
  fallback?: string;
  actions?: string[];
  action_display?: NodeActionDisplay[];
  required_opinion_actions?: string[];
  transfer_scope?: TransferScope | null;
  field_perm?: Record<string, string>;
  auto?: Record<string, unknown>;
}

export interface DesignEdge {
  from: string;
  to: string;
  condition?: ConditionGroup;
  default?: boolean;
}

export interface FlowDesign {
  settings?: Record<string, unknown>;
  nodes: DesignNode[];
  edges: DesignEdge[];
}

export interface CanvasNodeData extends Record<string, unknown> {
  label: string;
  nodeType: string;
  assignees: string[];
  assigneeSource?: string;
  assigneeValue?: string | number;
  orSign: boolean;
  multiMode?: string;
  actions?: string[];
  actionDisplay?: NodeActionDisplay[];
  requiredOpinionActions?: string[];
  transferScope?: TransferScope | null;
  notify?: boolean;
  fieldPerm?: Record<string, string>;
  auto?: Record<string, unknown>;
  original?: DesignNode;
  condition?: ConditionGroup;
}

export interface CanvasNode {
  id: string;
  type?: string;
  position: { x: number; y: number };
  data: CanvasNodeData;
  style?: Record<string, string>;
}

export interface CanvasEdge {
  id: string;
  type?: string;
  source: string;
  target: string;
  selected?: boolean;
  data?: { condition?: ConditionGroup; isDefault?: boolean };
}

export const DEMO_FLOW: FlowDesign = {
  nodes: [
    { id: 'start', type: 'start', name: '开始' },
    { id: 'submit', type: 'submit', name: '提单' },
    {
      id: 'approve',
      type: 'approval',
      name: '部门审批',
      assignee: { source: 'users', value: ['alice', 'bob'] },
      multi: { mode: 'any' },
      fallback: 'admin',
    },
    {
      id: 'handle',
      type: 'handle',
      name: '处理',
      assignee: { source: 'users', value: ['handler'] },
      fallback: 'admin',
    },
    { id: 'end', type: 'end', name: '结束' },
  ],
  edges: [
    { from: 'start', to: 'submit' },
    { from: 'submit', to: 'approve' },
    { from: 'approve', to: 'handle' },
    { from: 'handle', to: 'end' },
  ],
};

export const canvasFromDesign = (design: FlowDesign): { nodes: CanvasNode[]; edges: CanvasEdge[] } => ({
  nodes: design.nodes.map((node, index) => ({
    id: node.id,
    type: 'itsm',
    position: { x: index * 212, y: 0 },
    data: {
      label: node.name || node.id,
      nodeType: node.type,
      assignees: Array.isArray(node.assignee?.value) ? node.assignee.value : [],
      assigneeSource: node.assignee?.source || 'users',
      assigneeValue: Array.isArray(node.assignee?.value) ? undefined : node.assignee?.value,
      orSign: node.multi?.mode === 'any',
      multiMode: node.multi?.mode,
      fieldPerm: node.field_perm,
      actions: node.actions,
      actionDisplay: node.action_display === undefined ? undefined : readNodeActionDisplay(node.action_display),
      requiredOpinionActions: node.required_opinion_actions,
      transferScope: node.transfer_scope,
      auto: node.auto,
      original: node,
    },
  })),
  edges: design.edges.map((edge, index) => ({
    id: `e${index}`,
    type: 'smoothstep',
    source: edge.from,
    target: edge.to,
    data: { condition: edge.condition, isDefault: edge.default },
  })),
});

export const designFromCanvas = (nodes: CanvasNode[], edges: CanvasEdge[]): FlowDesign => ({
  nodes: nodes.map((node) => {
    const designNode: DesignNode = {
      ...node.data.original,
      id: node.id,
      type: node.data.nodeType,
      name: node.data.label,
    };
    if (['approval', 'handle', 'manual', 'submit', 'subprocess_handle'].includes(node.data.nodeType) && (node.data.original?.assignee || node.data.assignees.length || node.data.assigneeValue || node.data.assigneeSource === 'service_group')) {
      const source = node.data.assigneeSource || 'users';
      const value = source === 'users' ? node.data.assignees : node.data.assigneeValue ?? '';
      designNode.assignee = { source, value: source === 'service_group' ? [] : value };
      designNode.fallback = source === 'service_group' ? 'block' : node.data.original?.fallback || 'block';
    }
    if (node.data.auto) designNode.auto = node.data.auto;
    if (node.data.multiMode) {
      if (node.data.multiMode === 'single') delete designNode.multi;
      else designNode.multi = { ...designNode.multi, mode: node.data.multiMode };
    } else if (node.data.orSign) {
      designNode.multi = { mode: 'any' };
    }
    if (node.data.actions !== undefined) {
      designNode.actions = node.data.actions;
    }
    if (node.data.actionDisplay !== undefined) {
      designNode.action_display = node.data.actionDisplay;
    }
    if (node.data.requiredOpinionActions !== undefined) {
      designNode.required_opinion_actions = node.data.requiredOpinionActions;
    }
    if (node.data.transferScope === null) {
      delete designNode.transfer_scope;
    } else if (node.data.transferScope) {
      designNode.transfer_scope = node.data.transferScope;
    }
    if (node.data.fieldPerm) {
      designNode.field_perm = node.data.fieldPerm;
    }
    return designNode;
  }),
  edges: edges.map((edge) => ({
    from: edge.source,
    to: edge.target,
    ...(edge.data?.condition ? { condition: edge.data.condition } : {}),
    ...(edge.data?.isDefault ? { default: true } : {}),
  })),
});
