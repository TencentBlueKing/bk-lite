export interface RelatedTopologyTreeNode {
  inst_uuid?: string;
  inst_name?: string;
  model_id?: string;
  model_name?: string;
  asst_id?: string;
  asst_name?: string;
  monitor_id?: string;
  alert_count?: number | null;
  max_level?: string | null;
  children?: RelatedTopologyTreeNode[];
  [key: string]: unknown;
}

export interface RelatedTopologyResponse {
  center_inst_uuid: string;
  src_result?: RelatedTopologyTreeNode | Record<string, never>;
  dst_result?: RelatedTopologyTreeNode | Record<string, never>;
}

export interface RelatedTopologyGraphNode {
  id: string;
  name: string;
  modelId: string;
  modelName: string;
  isCenter: boolean;
  monitorId: string;
  alertCount: number | null;
  maxLevel: string | null;
  x: number;
  y: number;
}

export interface RelatedTopologyGraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

export interface RelatedTopologyGraphModel {
  centerId: string;
  empty: boolean;
  nodes: RelatedTopologyGraphNode[];
  edges: RelatedTopologyGraphEdge[];
}
