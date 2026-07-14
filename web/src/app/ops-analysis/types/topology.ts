import { DirItem } from './index';
import type { ParamItem } from './dataSource';
import type {
  ValueConfig,
  UnifiedFilterDefinition,
  TableConfig,
  FilterBindings,
  RuntimeParamControl,
} from './dashBoard';
import type { Graph as X6Graph, Cell, Node, Edge } from '@antv/x6';
import type { Attr } from '@antv/x6/es/registry/attr';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';

// 基础几何类型
export interface Point {
  x: number;
  y: number;
}

// 状态管理相关类型
export interface GraphState {
  instance: X6Graph | null;
  scale: number;
  selectedCells: string[];
  isSelectMode: boolean;
  isEditMode: boolean;
  collapsed: boolean;
}

export interface ContextMenuState {
  nodeId: string;
  visible: boolean;
  position: { x: number; y: number };
  targetType: 'node' | 'edge';
}

export interface EdgeConfigState {
  visible: boolean;
  data: EdgeData | null;
}

export type TopologyRawData = unknown;
export type TopologyRecord = Record<string, unknown>;
export type EdgeConnectionType = 'none' | 'single' | 'double';
export type EdgeLineStyle = 'line' | 'dotted' | 'point';

export interface EdgeStyleConfig {
  lineColor?: string;
  lineWidth?: number;
  lineStyle?: EdgeLineStyle;
  enableAnimation?: boolean;
}

export interface TopologyPortConfig {
  groups: Record<string, {
    position: {
      name: string;
      args?: Record<string, string>;
    };
    attrs: Attr.CellAttrs;
  }>;
  items: Array<{
    id: string;
    group: string;
  }>;
}

export interface TopologyEdgeVisual {
  attrs: {
    line: Attr.ComplexAttrs;
  };
  labels: Edge.Label[];
}

export interface NodeStyleConfig {
  width?: number;
  height?: number;
  backgroundColor?: string;
  borderColor?: string;
  borderWidth?: number;
  iconPadding?: number;
  lineType?: 'solid' | 'dashed' | 'dotted';
  shapeType?: 'rectangle' | 'circle';
  textColor?: string;
  fontSize?: number;
  fontWeight?: string | number;
  nameColor?: string;
  nameFontSize?: number;
  textDirection?: 'top' | 'bottom' | 'left' | 'right';
  thresholdColors?: Array<{
    value: string;
    color: string;
  }>;
}

export interface NodeEditState {
  visible: boolean;
  data: TopologyNodeData | null;
}

// 节点相关类型扩展
export interface TopologyNodeData {
  id?: string;
  type: string;
  name: string;
  unit?: string;
  conversionFactor?: number;
  decimalPlaces?: number;
  position?: Point;
  zIndex?: number; 
  logoType?: 'default' | 'custom';
  logoIcon?: string;
  logoUrl?: string;
  description?: string;
  // 运行时状态字段
  isLoading?: boolean;
  hasError?: boolean;
  errorMessage?: string;
  rawData?: TopologyRawData;
  isPlaceholder?: boolean;
  isNewNode?: boolean; 
  // 值配置 - 包含数据源相关配置
  valueConfig?: ValueConfig;
  // 样式配置
  styleConfig?: NodeStyleConfig;
}

// 图形实例操作类型
export interface GraphOperations {
  getCells(): Cell[];
  getNodes(): Node[];
  getEdges(): Edge[];
  getCellById(id: string): Cell | null;
  clientToLocal(clientX: number, clientY: number): Point;
  addEdge(edgeConfig: Edge.Metadata | Edge): Edge;
}

// 状态管理相关类型
export interface TopologyState {
  graphInstance: X6Graph | null;
  contextMenuNodeId: string | null;
  setContextMenuVisible: (visible: boolean) => void;
  isEditMode: boolean;
  currentEdgeData: EdgeData | null;
  setCurrentEdgeData: (data: EdgeData | null) => void;
  isDrawingRef: React.MutableRefObject<boolean>;
  drawingEdgeRef: React.MutableRefObject<Edge | null>;
  updateDrawingState: (isDrawing: boolean) => void;
  setEdgeConfigVisible: (visible: boolean) => void;

  // 节点编辑相关状态
  setEditingNodeData: (data: TopologyNodeData | null) => void;
  setNodeEditVisible: (visible: boolean) => void;

  // 视图配置相关状态  
  setViewConfigVisible: (visible: boolean) => void;
}

// 菜单操作类型
export interface MenuClickEvent {
  key: string;
}

// 端口配置类型
export interface PortPosition {
  x: number;
  y: number;
}

export interface PortPositions {
  top: PortPosition;
  bottom: PortPosition;
  left: PortPosition;
  right: PortPosition;
}

// Hook 返回类型
export interface UseContextMenuAndModalReturn {
  handleEdgeConfigConfirm: (values: {
    lineType: 'common_line' | 'network_line';
    lineName?: string;
    styleConfig?: EdgeStyleConfig;
  }) => void;
  closeEdgeConfig: () => void;
  handleMenuClick: (event: MenuClickEvent) => void;
}


export interface EdgeData {
  id?: string;
  lineType: 'common_line' | 'network_line';
  lineName?: string;
  arrowDirection?: 'none' | 'single' | 'double';
  styleConfig?: EdgeStyleConfig;
  config?: TopologyRecord;
  sourceNode: { id: string; name: string };
  targetNode: { id: string; name: string };
  sourceInterface?: InterfaceConfig;
  targetInterface?: InterfaceConfig;
}

export interface EdgeCreationData {
  lineType: 'common_line' | 'network_line';
  lineName?: string;
  sourceInterface?: string;
  targetInterface?: string;
  config?: TopologyRecord;
}

// 节点类型定义
export type NodeTypeId = 'single-value' | 'icon' | 'chart' | 'basic-shape' | 'text';

export interface NodeConfPanelProps {
  nodeType: NodeTypeId;
  readonly?: boolean;
  visible?: boolean;
  title?: string;
  builtinNamespaceId?: number;
  onClose?: () => void;
  onConfirm?: (values: NodeConfigFormValues) => void;
  onCancel?: () => void;
  editingNodeData?: TopologyNodeData | null;
}

export interface ContextMenuProps {
  visible: boolean;
  position: { x: number; y: number };
  isEditMode?: boolean;
  targetType?: 'node' | 'edge';
  onMenuClick: (e: { key: string }) => void;
}

// 边序列化数据结构
export interface SerializedEdge {
  id?: string;
  source: string;
  target: string;
  sourcePort?: string;
  targetPort?: string;
  lineType?: string;
  lineName?: string;
  sourceInterface?: string;
  targetInterface?: string;
  arrowDirection?: 'none' | 'single' | 'double';
  config?: unknown;
  styleConfig?: {
    lineColor?: string;
    lineWidth?: number;
    lineStyle?: 'line' | 'dotted' | 'point';
    enableAnimation?: boolean;
  };
  vertices?: Array<{ x: number; y: number }>;
}

// 数据树节点结构
export interface TreeNode {
  title: React.ReactNode;
  key: string;
  value?: string;
  isLeaf?: boolean;
  children?: TreeNode[];
}

export interface InterfaceConfig {
  type: 'existing' | 'custom';
  value: string;
}

export interface EdgeConfigPanelProps {
  visible: boolean;
  readonly?: boolean;
  edgeData: EdgeData | null;
  onClose: () => void;
  onConfirm?: (values: EdgeData) => void;
}

export interface NodeSidebarProps {
  collapsed: boolean;
  isEditMode?: boolean;
  graphInstance?: X6Graph;
  setCollapsed: (collapsed: boolean) => void;
  onShowNodeConfig?: (nodeType: NodeType, dropPosition?: DropPosition) => void;
  onShowChartSelector?: (dropPosition?: DropPosition) => void;
}

export interface NodeType {
  id: string;
  name: string;
  icon: React.ReactNode;
  description?: string;
}

export interface DropPosition {
  x: number;
  y: number;
}

export interface ToolbarProps {
  isSelectMode: boolean;
  isEditMode?: boolean;
  isFullscreen?: boolean;
  selectedTopology?: DirItem | null;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onEdit: () => void;
  onSave: () => void;
  onFullscreenToggle: () => void;
  onFit: () => void;
  onDelete: () => void;
  onSelectMode: () => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
  onRefresh?: () => void;
  onFrequencyChange?: (frequency: number) => void;
  onCancel?: () => void;
  onFilterConfig?: () => void;
}

// ViewConfig 表单值类型
export interface ViewConfigFormValues {
  name: string;
  description?: string;
  chartType?: string;
  chartThemeMode?: OpsChartThemeMode;
  dataSource?: number | string;
  compare?: boolean;
  dataSourceParams?: ParamItem[];
  filterBindings?: FilterBindings;
  selectedFields?: string[];
  topNLabelField?: string;
  topNValueField?: string;
  runtimeParamControl?: RuntimeParamControl;
  unit?: string;
  conversionFactor?: number;
  decimalPlaces?: number;
  gaugeMin?: number;
  gaugeMax?: number;
  gaugeShape?: 'semicircle' | 'circle';
  thresholdColors?: Array<{
    value: string;
    color: string;
  }>;
  tableConfig?: TableConfig;
}

// 节点配置表单值类型
export interface NodeConfigFormValues {
  name?: string;
  description?: string;
  logoType?: 'default' | 'custom';
  logoIcon?: string;
  logoUrl?: string;
  compare?: boolean;
  selectedFields?: string[];
  chartType?: string;
  dataSource?: number | string;
  dataSourceParams?: ParamItem[];
  builtinNamespaceId?: number;
  topNLabelField?: string;
  topNValueField?: string;
  runtimeParamControl?: RuntimeParamControl;
  width?: number;
  height?: number;
  backgroundColor?: string;
  borderColor?: string;
  borderWidth?: number;
  textColor?: string;
  fontSize?: number;
  fontWeight?: string | number;
  iconPadding?: number;
  lineType?: 'solid' | 'dashed' | 'dotted';
  shapeType?: 'rectangle' | 'circle';
  nameColor?: string;
  nameFontSize?: number;
  textDirection?: 'top' | 'bottom' | 'left' | 'right';
  unit?: string;
  unitId?: string;
  valueMappings?: import('@/app/ops-analysis/utils/valueMapping').ValueMapping[];
  conversionFactor?: number;
  decimalPlaces?: number;
  thresholdColors?: Array<{
    value: string;
    color: string;
  }>;
}

// Topology 组件 Props 和 Ref 类型
export interface TopologyProps {
  selectedTopology?: DirItem | null;
}

export interface TopologyRef {
  hasUnsavedChanges: () => boolean;
}

export interface TopologyViewSets {
  nodes: TopologyNodeData[];
  edges: SerializedEdge[];
  filters?: UnifiedFilterDefinition[];
}

// 节点基础数据类型
export interface BaseNodeData {
  id: string;
  x: number;
  y: number;
  shape: string;
  label: string;
  data: TopologyNodeData;
}

// X6 图形属性配置
// 创建节点返回的类型
export type CreatedNodeConfig = BaseNodeData &
  Omit<Node.Metadata, 'attrs' | 'data' | 'ports'> & {
  width?: number;
  height?: number;
  attrs?: Attr.CellAttrs;
  ports?: TopologyPortConfig;
};

export interface TopologySaveData {
  name: string;
  desc?: string;
  view_sets: TopologyViewSets;
}
