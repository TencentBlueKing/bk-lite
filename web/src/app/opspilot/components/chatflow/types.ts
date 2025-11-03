import type { Node } from '@xyflow/react';

export interface ChatflowNodeData {
  label: string;
  type: 'celery' | 'restful' | 'openai' | 'agents' | 'condition' | 'http' | 'notification' | 'enterprise_wechat';
  config?: any;
  description?: string;
  [key: string]: unknown;
}

export interface ChatflowNode extends Node {
  data: ChatflowNodeData;
}

export interface ChatflowEditorRef {
  clearCanvas: () => void;
}

export interface ChatflowEditorProps {
  onSave?: (nodes: Node[], edges: import('@xyflow/react').Edge[]) => void;
  initialData?: { nodes: Node[], edges: import('@xyflow/react').Edge[] } | null;
}

export const isChatflowNode = (node: Node): node is ChatflowNode => {
  return node.data &&
         typeof (node.data as any).label === 'string' &&
         typeof (node.data as any).type === 'string';
}
