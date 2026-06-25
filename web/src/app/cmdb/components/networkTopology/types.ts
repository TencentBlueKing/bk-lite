import type { ReactNode } from 'react';

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

export interface NetworkTopologyCanvasProps {
  nodes: NetworkTopologyNode[];
  links: NetworkTopologyLink[];
  centerId?: string;
  layoutMode: NetworkTopologyLayoutMode;
  labels: {
    layoutHierarchical: string;
    layoutForce: string;
    layoutCircular: string;
    zoomOut: string;
    zoomIn: string;
    exportImage: string;
    refresh: string;
  };
  selectedNodeId?: string;
  activeNodeIds?: Set<string> | string[];
  activeLinkIds?: Set<string> | string[];
  dimInactive?: boolean;
  loading?: boolean;
  refreshLoading?: boolean;
  error?: string;
  emptyText?: ReactNode;
  truncatedText?: ReactNode;
  exportFileName?: string;
  onLayoutChange?: (mode: NetworkTopologyLayoutMode) => void;
  onRefresh?: () => void;
  onBlankClick?: () => void;
  onNodeClick?: (node: NetworkTopologyNode) => void;
  renderPopover?: (node: NetworkTopologyNode) => ReactNode;
  renderContextMenu?: (
    node: NetworkTopologyNode,
    closeMenu: () => void,
  ) => ReactNode;
}
