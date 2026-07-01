export type NetworkTopologyLayoutMode = 'hierarchical' | 'force' | 'circular';

export type NetworkTopologyNodeStatus =
  | 'normal'
  | 'warning'
  | 'error'
  | 'critical';

export interface NetworkTopologyNode {
  id: string;
  modelId: string;
  name: string;
  subtitle?: string;
  hop?: number;
  status?: NetworkTopologyNodeStatus;
  alertCount?: number;
  pulse?: boolean;
  icon?: string;
}

export interface NetworkTopologyLink {
  id: string;
  source: string;
  target: string;
  sourcePort?: string;
  targetPort?: string;
}

export interface NetworkTopologyPositionedNode extends NetworkTopologyNode {
  x: number;
  y: number;
}

export interface NetworkTopologyPositionedLink extends NetworkTopologyLink {
  curveOffset: number;
}

export interface NetworkTopologyLayoutResult {
  nodes: NetworkTopologyPositionedNode[];
  links: NetworkTopologyPositionedLink[];
}
