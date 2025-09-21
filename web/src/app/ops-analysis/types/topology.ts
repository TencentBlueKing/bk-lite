import { DirItem } from './index';
import { DataSourceParam } from './dashBoard';
import type { Graph as X6Graph, Cell, Node, Edge } from '@antv/x6';

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

export interface TextEditState {
  isEditing: boolean;
  nodeId: string | null;
  tempInput: string;
  position: { x: number; y: number };
  inputWidth: number;
  originalText: string;
}

export interface EdgeConfigState {
  visible: boolean;
  data: EdgeData | null;
}

export interface NodeEditState {
  visible: boolean;
  data: any;
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
  logoType?: string;
  logoIcon?: string;
  logoUrl?: string;
  description?: string;
  // 运行时状态字段
  isLoading?: boolean;
  hasError?: boolean;
  rawData?: any;
  isPlaceholder?: boolean;
  // 值配置 - 包含数据源相关配置
  valueConfig?: {
    chartType?: string;
    dataSource?: number;
    dataSourceParams?: DataSourceParam[];
    selectedFields?: string[];
  };
  // 样式配置
  styleConfig?: {
    width?: number;
    height?: number;
    backgroundColor?: string;
    borderColor?: string;
    borderWidth?: number;
    renderEffect?: 'normal' | 'glass';
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
  };
}

// 图形实例操作类型
export interface GraphOperations {
  getCells(): Cell[];
  getNodes(): Node[];
  getEdges(): Edge[];
  getCellById(id: string): Cell | null;
  clientToLocal(clientX: number, clientY: number): Point;
  addEdge(edgeConfig: any): Edge;
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
  setEditingNodeData: (data: any) => void;
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
    styleConfig?: {
      lineColor?: string;
      lineWidth?: number;
      lineStyle?: 'line' | 'dotted' | 'point';
      enableAnimation?: boolean;
    }
  }) => void;
  closeEdgeConfig: () => void;
  handleMenuClick: (event: MenuClickEvent) => void;
}


export interface EdgeData {
  id?: string;
  lineType: 'common_line' | 'network_line';
  lineName?: string;
  arrowDirection?: 'none' | 'single' | 'double';
  styleConfig?: {
    lineColor?: string;
    lineWidth?: number;
    lineStyle?: 'line' | 'dotted' | 'point';
    enableAnimation?: boolean;
  };
  config?: any;
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
  config?: any;
}

export interface NodeConfPanelProps {
  nodeType: 'single-value' | 'icon' | 'chart' | 'basic-shape';
  readonly?: boolean;
  visible?: boolean;
  title?: string;
  onClose?: () => void;
  onConfirm?: (values: NodeConfigFormValues) => void;
  onCancel?: () => void;
  editingNodeData?: any;
}

export interface ContextMenuProps {
  visible: boolean;
  position: { x: number; y: number };
  isEditMode?: boolean;
  targetType?: 'node' | 'edge';
  onMenuClick: (e: { key: string }) => void;
}
interface InterfaceConfig {
  type: 'existing' | 'custom';
  value: string;
}

export interface EdgeConfigPanelProps {
  visible: boolean;
  readonly?: boolean;
  edgeData: EdgeData | null;
  onClose: () => void;
  onConfirm?: (values: any) => void;
}

export interface SidebarProps {
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
  description: string;
}

export interface DropPosition {
  x: number;
  y: number;
}

export interface TextEditInputProps {
  isEditingText: boolean;
  editPosition: { x: number; y: number };
  inputWidth: number;
  tempTextInput: string;
  setTempTextInput: (text: string) => void;
  finishTextEdit: () => void;
  cancelTextEdit: () => void;
}

export interface ToolbarProps {
  isSelectMode: boolean;
  isEditMode?: boolean;
  selectedTopology?: DirItem | null;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onEdit: () => void;
  onSave: () => void;
  onFit: () => void;
  onDelete: () => void;
  onSelectMode: () => void;
  onAddText: () => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
}

// ViewConfig 表单值类型
export interface ViewConfigFormValues {
  name: string;
  description?: string;
  chartType: string;
  dataSource: number;
  dataSourceParams?: Array<{
    name: string;
    value: string | number | boolean | object | null;
    type: string;
  }>;
}

// 节点配置表单值类型
export interface NodeConfigFormValues {
  name?: string;
  logoType?: 'default' | 'custom';
  logoIcon?: string;
  logoUrl?: string;
  selectedFields?: string[];
  chartType?: string;
  dataSource?: number;
  dataSourceParams?: Array<{
    name: string;
    value: string | number | boolean | object | null;
    type: string;
  }>;
  width?: number;
  height?: number;
  backgroundColor?: string;
  borderColor?: string;
  borderWidth?: number;
  textColor?: string;
  fontSize?: number;
  iconPadding?: number;
  lineType?: string;
  shapeType?: string;
  nameColor?: string;
  nameFontSize?: number;
  unit?: string;
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
interface NodeAttrs {
  body?: Record<string, any>;
  image?: Record<string, any>;
  label?: Record<string, any>;
  nameLabel?: Record<string, any>;
}

// 创建节点返回的类型
export interface CreatedNodeConfig extends BaseNodeData {
  width?: number;
  height?: number;
  attrs?: NodeAttrs;
  ports?: any;
}