export type SceneWidgetType = 'networkStatusTopology';

export type NetworkStatusTopologyLayoutMode =
  | 'hierarchical'
  | 'force'
  | 'circular';

export type NetworkStatusTopologyPoint = { x: number; y: number };

/** 单个布局模式下的手工几何 */
export interface NetworkStatusTopologyModeLayout {
  /** 节点 id → 布局算法坐标，覆盖算法布局结果 */
  nodePositions?: Record<string, NetworkStatusTopologyPoint>;
  /** 连线 id → 手工折点；优先于自动并行边偏移 */
  linkVertices?: Record<string, NetworkStatusTopologyPoint[]>;
}

export interface NetworkStatusTopologyConfig {
  modelId: string;
  instId: string;
  depth: number;
  /** 可选；缺省视为 hierarchical */
  layoutMode?: NetworkStatusTopologyLayoutMode;
  /** 按布局模式分桶的手工几何；写盘只使用此字段 */
  layoutByMode?: Partial<
    Record<NetworkStatusTopologyLayoutMode, NetworkStatusTopologyModeLayout>
  >;
  /**
   * @deprecated 仅本地旧草稿读兼容；新写入不再输出。
   * 若存在且 layoutByMode 无对应桶，归入当时 layoutMode（缺省 hierarchical）。
   */
  nodePositions?: Record<string, NetworkStatusTopologyPoint>;
  /**
   * @deprecated 仅本地旧草稿读兼容；新写入不再输出。
   */
  linkVertices?: Record<string, NetworkStatusTopologyPoint[]>;
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
