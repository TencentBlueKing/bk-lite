import { TopologyNodeData } from './topology';
import type { ParamItem, DatasourceItem } from './dataSource';
import type { ValueMapping } from '@/app/ops-analysis/utils/valueMapping';
import type { Dayjs } from 'dayjs';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import type {
  NetworkStatusTopologyConfig,
  SceneWidgetType,
} from './sceneWidget';

export type FilterType = 'selector' | 'fixed';

export interface EChartsInstance {
  dispatchAction: (action: {
    type: string;
    name?: string;
    [key: string]: unknown;
  }) => void;
  setOption: (option: unknown) => void;
  resize: () => void;
  dispose: () => void;
  [key: string]: unknown;
}

export interface TimeConfig {
  selectValue: number;
  rangePickerVaule: [Dayjs, Dayjs] | null;
}

export interface OtherConfig {
  timeSelector?: TimeConfig;
  [key: string]: unknown;
}

export interface TimeRangeData {
  start: number;
  end: number;
  selectValue: number;
  rangePickerVaule: [Dayjs, Dayjs] | null;
}

export interface LayoutChangeItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface AddComponentConfig {
  name?: string;
  description?: string;
  defaultWidth?: number;
  defaultHeight?: number;
  dataSource?: string | number;
  chartType?: string;
  sceneWidgetType?: SceneWidgetType;
  networkStatusTopology?: NetworkStatusTopologyConfig;
  dataSourceParams?: ParamItem[];
  tableConfig?: TableConfig;
}

/** 表格筛选字段配置（组件级别） */
export interface TableFilterFieldConfig {
  key: string;
  label: string;
  inputType: 'keyword' | 'time_range';
}

/** 表格列配置（组件级别） */
export interface TableColumnConfigItem {
  key: string;
  title: string;
  visible: boolean;
  order: number;
  width?: number;
  columnType?: 'data' | 'actions';
}

/** 表格组件配置 */
export interface TableConfig {
  filterFields?: TableFilterFieldConfig[];
  columns?: TableColumnConfigItem[];
}

import { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';

export interface ValueConfig {
  chartType?: string;
  sceneWidgetType?: SceneWidgetType;
  networkStatusTopology?: NetworkStatusTopologyConfig;
  chartThemeMode?: OpsChartThemeMode;
  dataSource?: string | number;
  compare?: boolean;
  params?: Record<string, string | number | boolean | [number, number] | null>;
  dataSourceParams?: ParamItem[];
  tableConfig?: TableConfig;
  filterBindings?: FilterBindings;
  selectedFields?: string[];
  topNLabelField?: string;
  topNValueField?: string;
  unit?: string;
  /** 结构化单位 id（bytesIEC/bps/ms/percent/short…）。设置后启用单位库自动量纲；
   *  未设置时回退到自由文本 unit（向后兼容）。 */
  unitId?: string;
  /** 值映射规则（值→文本/色），命中时覆盖数值展示与颜色。 */
  valueMappings?: ValueMapping[];
  conversionFactor?: number;
  decimalPlaces?: number;
  thresholdColors?: ThresholdColorConfig[];
  gaugeMin?: number;
  gaugeMax?: number;
  gaugeShape?: 'semicircle' | 'circle';
  actions?: DashboardActionConfig[];
}

export interface ScreenRenderContext {
  enabled: boolean;
  fitScale: number;
  screenDensity: number;
  screenUiScale: number;
  widgetDensity: number;
  widgetUiScale: number;
}

export interface DashboardActionParamMapping {
  key: string;
  source: 'rowField' | 'fixed';
  sourceKey?: string;
  value?: string | number | boolean | null;
}

export interface DashboardActionConfig {
  columnKey: string;
  text: string;
  url?: string;
  openMode?: 'sameTab' | 'newTab';
  params?: DashboardActionParamMapping[];
}

export interface WidgetConfig extends ValueConfig {
  name: string;
  description?: string;
  defaultWidth?: number;
  defaultHeight?: number;
  tableConfig?: TableConfig;
}

export interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  name: string;
  description?: string;
  valueConfig?: ValueConfig;
}

export interface DashboardWidgetLayoutItem extends LayoutItem {
  itemType?: 'widget' | 'sceneWidget';
  groupId?: string | null;
}

export interface DashboardGroupLayoutItem {
  i: string;
  itemType: 'group';
  x: number;
  y: number;
  w: number;
  h: number;
  name: string;
  description?: string;
}

export type DashboardLayoutItem = DashboardWidgetLayoutItem | DashboardGroupLayoutItem;

export type ViewConfigItem = LayoutItem | TopologyNodeData;

export interface ViewConfigProps {
  open: boolean;
  item: ViewConfigItem;
  onConfirm?: (values: WidgetConfig) => void;
  onClose?: () => void;
  builtinNamespaceId?: number;
  showChartThemeMode?: boolean;
}

export interface ComponentSelectorConfigItem extends DatasourceItem {
  chartType: string;
  dataSource?: string | number;
  defaultWidth: number;
  defaultHeight: number;
  sceneWidgetType?: SceneWidgetType;
}

export interface ComponentSelectorProps {
  visible: boolean;
  onCancel: () => void;
  onOpenConfig?: (item: ComponentSelectorConfigItem) => void;
}

export interface BaseWidgetProps {
  config?: ValueConfig;
  refreshKey?: number;
  onDataChange?: (data: unknown) => void;
  onReady?: (hasData?: boolean) => void;
}

export interface WidgetMeta {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  defaultConfig?: any;
}

export interface WidgetDefinition {
  meta: WidgetMeta;
  configComponent?: React.ComponentType<any>;
}

// ==================== 统一筛选相关类型 ====================

/** 时间范围值 */
export interface TimeRangeValue {
  start: string; // ISO 8601 格式
  end: string;
  selectValue?: number; // 快捷选择的分钟数，0表示自定义时间
}

/** 筛选值类型 */
export type FilterValue = string | number | TimeRangeValue | null;

/** 筛选选项（用于下拉选择） */
export interface FilterOption {
  label: string;
  value: string;
}

/** 统一筛选项定义 */
export interface UnifiedFilterDefinition {
  id: string;
  key: string; // 参数 key（如 "time_range", "env", "namespace"）
  name: string; // 显示名称（用户可编辑）
  type: 'timeRange' | 'string'; // 参数类型，用于绑定匹配
  defaultValue?: FilterValue; // 默认值
  order: number; // 显示顺序
  enabled: boolean; // 是否启用
  inputMode?: 'input' | 'select' | 'radio' | 'organization'; // 输入方式（仅 string 类型有效）
  options?: FilterOption[]; // 选项（仅 inputMode 为 select/radio 时有效）
}

/** Dashboard.filters 运行时结构（hook 内部使用） */
export interface DashboardFiltersState {
  definitions: UnifiedFilterDefinition[]; // 统一筛选项定义列表
  values: Record<string, FilterValue>; // 当前筛选值 { [filterId]: value }
}

/** Dashboard.filters 存储结构（直接数组） */
export type DashboardFilters = UnifiedFilterDefinition[];

/** 组件级绑定配置 */
export interface FilterBindings {
  [filterId: string]: boolean; // filterId -> 是否绑定
}

/** 扫描结果结构（用于配置弹窗） */
export interface ScannedFilterParam {
  key: string;
  type: 'string' | 'timeRange';
  componentCount: number;
  sampleAlias: string;
  sampleDefaultValue: FilterValue;
}

/** 绑定校验结果 */
export interface BindingValidationResult {
  filterId: string;
  isValid: boolean;
  reason?: 'filter_not_found' | 'param_not_found' | 'type_mismatch';
}
