import type { ConditionGroup } from '../types';

export interface DesignNode {
  id: string;
  type: string;
  name: string;
  assignee?: { source: string; value: string[] };
  multi?: { mode: string };
  fallback?: string;
  actions?: string[];
  field_perm?: Record<string, string>;
}

export interface DesignEdge {
  from: string;
  to: string;
  condition?: ConditionGroup;
  default?: boolean;
}

export interface FlowDesign {
  nodes: DesignNode[];
  edges: DesignEdge[];
}

export interface CanvasNodeData extends Record<string, unknown> {
  label: string;
  nodeType: string;
  assignees: string[];
  orSign: boolean;
  actions?: string[];
  notify?: boolean;
  fieldPerm?: Record<string, string>;
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
      assignees: node.assignee?.value || [],
      orSign: node.multi?.mode === 'any',
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
      id: node.id,
      type: node.data.nodeType,
      name: node.data.label,
    };
    if (node.data.assignees.length > 0) {
      designNode.assignee = { source: 'users', value: node.data.assignees };
      designNode.fallback = 'admin';
    }
    if (node.data.orSign) {
      designNode.multi = { mode: 'any' };
    }
    if (node.data.actions?.length) {
      designNode.actions = node.data.actions;
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
