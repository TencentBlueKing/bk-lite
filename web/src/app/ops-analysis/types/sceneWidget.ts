export type SceneWidgetType = 'networkStatusTopology';

export interface NetworkStatusTopologyConfig {
  modelId: string;
  instId: string;
  depth: number;
}

export type NetworkNodeStatus = 'normal' | 'warning' | 'error' | 'critical';

export interface NetworkStatusTopologyNode {
  id: string;
  model_id: string;
  name: string;
  hop: number;
  status: NetworkNodeStatus;
  severity?: 'warning' | 'error' | 'critical' | null;
  color?: 'green' | 'yellow' | 'red';
  pulse: boolean;
  alert_count: number;
  icon?: string;
  resource_type?: string;
  resource_id?: string;
  [key: string]: unknown;
}

export interface NetworkStatusTopologyLink {
  id?: string;
  source?: string;
  target?: string;
  source_device?: string | number;
  target_device?: string | number;
  relationship_id?: string | number;
  source_port?: string;
  target_port?: string;
  source_inst_name?: string;
  target_inst_name?: string;
  [key: string]: unknown;
}

export interface NetworkStatusTopologyResponse {
  center_id: string;
  center_model_id?: string;
  nodes: NetworkStatusTopologyNode[];
  links: NetworkStatusTopologyLink[];
  truncated?: boolean;
  node_limit?: number;
}
