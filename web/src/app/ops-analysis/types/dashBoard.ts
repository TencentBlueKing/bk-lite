import { TopologyNodeData } from './topology';
import type {
  ParamItem,
  DatasourceItem,
  InputControlConfig,
} from './dataSource';
import type { ValueMapping } from '@/app/ops-analysis/utils/valueMapping';
import type {
  CardListConfig,
  CardListLeadingConfig,
} from '@/app/ops-analysis/utils/cardList';

export type { CardListConfig, CardListLeadingConfig };
import type { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';
import type { Dayjs } from 'dayjs';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import type {
  ApplicationTopologyConfig,
  NetworkStatusTopologyConfig,
  RelatedTopologyConfig,
  Room3DConfig,
  SceneWidgetType,
} from './sceneWidget';
import type { Application3DWallConfig } from '@/app/ops-analysis/utils/application3DWallConfig';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';
import type { DateRangeValue } from './dateRange';
import type { SingleValueStyleConfig } from '@/app/ops-analysis/utils/singleValueStyle';

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
  /**
   * 仪表盘横向格数。缺省或 12 表示按旧 12 列保存的 x/w；
   * 当前运行时为 24，打开旧盘时换算一次后写入 24。
   */
  gridCols?: number;
  /** 仪表盘行高（px）。缺省为旧版 60，当前为 30；换算后的布局保存时写入。 */
  gridRowHeight?: number;
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
  relatedTopology?: RelatedTopologyConfig;
  applicationTopology?: ApplicationTopologyConfig;
  room3D?: Room3DConfig;
  application3DWall?: Application3DWallConfig;
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
  /** 单元格展示形态；缺省为 text */
  cellType?: 'text' | 'colorBackground';
  /** 列级值映射（枚举/范围等 → 文案/颜色） */
  valueMappings?: ValueMapping[];
  /** 列级数值阈值配色 */
  cellThresholdColors?: ThresholdColorConfig[];
}

/** 表格组件配置 */
export interface TableConfig {
  filterFields?: TableFilterFieldConfig[];
  columns?: TableColumnConfigItem[];
}

export interface ValueConfig {
  chartType?: string;
  sceneWidgetType?: SceneWidgetType;
  networkStatusTopology?: NetworkStatusTopologyConfig;
  relatedTopology?: RelatedTopologyConfig;
  applicationTopology?: ApplicationTopologyConfig;
  room3D?: Room3DConfig;
  application3DWall?: Application3DWallConfig;
  chartThemeMode?: OpsChartThemeMode;
  dataSource?: string | number;
  compare?: boolean;
  compareMode?: 'percent' | 'value';
  params?: Record<string, string | number | boolean | [number, number] | null>;
  dataSourceParams?: ParamItem[];
  tableConfig?: TableConfig;
  filterBindings?: FilterBindings;
  selectedFields?: string[];
  /** 单值可选说明字段；未设置时不渲染说明行 */
  descriptionField?: string;
  topNLabelField?: string;
  topNValueField?: string;
  /** 从单个对象的多个数值字段拆成多行，并保持配置顺序。未配置时仍按数组排名。 */
  topNScalarFields?: Array<{ field: string; label?: string }>;
  /** 缺省 relative：条宽按当前列表最大值。absolute：按 barMax，没有则用 gaugeMax。 */
  barMode?: 'relative' | 'absolute';
  /** absolute 模式下的满分。条宽为 clamp(value, 0, barMax) / barMax。 */
  barMax?: number;
  dimensionField?: string;
  valueField?: string;
  /** 从标量对象取两个及以上字段合成饼图；已有数组饼图不受影响。 */
  pieScalarFields?: Array<{ field: string; label?: string }>;
  multiValueLabelField?: string;
  multiValueValueField?: string;
  nodeGraphIdentityMode?: 'ip' | 'service';
  nodeGraphSourceField?: string;
  nodeGraphTargetField?: string;
  nodeGraphValueField?: string;
  nodeGraphTargetPortField?: string;
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
  eventTimeline?: {
    sortOrder?: 'asc' | 'desc';
    timeField?: string;
    titleField?: string;
    descriptionField?: string;
    categoryField?: string;
    statusField?: string;
    linkField?: string;
  };
  radar?: {
    min?: number;
    max?: number;
    indicators?: Array<{
      key: string;
      label?: string;
    }>;
    arrayNameField?: string;
    arrayValueField?: string;
  };
  cardList?: CardListConfig;
  /** 旧表格操作列。读取时迁成 interaction，保存不再写回。 */
  actions?: DashboardActionConfig[];
  interaction?: WidgetInteractionLink;
  appearance?: ScreenWidgetAppearance;
  /** 单值样式。缺省字段保持旧外观，不需要迁移。 */
  singleStyle?: SingleValueStyleConfig;
}

export type ScreenWidgetFrame = 'panel' | 'bare';

export interface ScreenWidgetAppearance {
  frame?: ScreenWidgetFrame;
}

export interface ScreenRenderContext {
  enabled: boolean;
  fitScale: number;
  /** 大屏画布相对设计尺寸的横向、纵向拉伸。铺满适配时两者可以不同。 */
  scaleX?: number;
  scaleY?: number;
  screenDensity: number;
  screenUiScale: number;
  widgetDensity: number;
  widgetUiScale: number;
}

/** 旧操作列参数映射。只在读取时转成 interaction，配置界面不再编辑。 */
export interface DashboardActionParamMapping {
  key: string;
  source: 'rowField' | 'fixed';
  sourceKey?: string;
  value?: string | number | boolean | null;
}

/** 旧操作列。读取时只保留第一条并迁成 interaction，保存时删除。 */
export interface DashboardActionConfig {
  columnKey: string;
  text: string;
  url?: string;
  openMode?: 'sameTab' | 'newTab';
  params?: DashboardActionParamMapping[];
}

/** 组件只保留一条交互链接：标题行最右侧 >，或点击数据。 */
export type WidgetInteractionKind = 'title' | 'data';

export type WidgetInteractionOpenMode = 'sameTab' | 'newTab';

export interface WidgetInteractionLink {
  kind: WidgetInteractionKind;
  name: string;
  url: string;
  openMode: WidgetInteractionOpenMode;
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
  /** Dashboard keeps ViewConfig mounted and may pass undefined while closed. */
  item?: ViewConfigItem | null;
  onConfirm?: (values: WidgetConfig) => void;
  onClose?: () => void;
  builtinNamespaceId?: number;
  showChartThemeMode?: boolean;
  surface?: OpsAnalysisWidgetSurface;
  /** 拓扑不插入统一筛选变量，名称和描述保持普通输入框。 */
  filterTemplateTokens?: boolean;
  /** 拓扑和大屏数据表单不提供单值样式。仪表盘抽屉默认开启。 */
  showSingleValueStyle?: boolean;
  variant?: 'drawer' | 'panel';
  /** 大屏检查器切换数据/交互时复用同一份表单。 */
  configSection?: 'data' | 'interaction';
  /** 面板模式的页签在外部，交互校验失败时切回交互页。 */
  onConfigSectionChange?: (section: 'data' | 'interaction') => void;
  /** 大屏当前容器样式。样式页切换时单独传入，避免整表重开。 */
  screenFrame?: ScreenWidgetFrame;
  onDirtyChange?: (dirty: boolean) => void;
  /**
   * 样式页已经写在组件上的单值样式。只盖到预览配置。
   * 数据表单 includeSingleStyle 仍为 false，提交不会带上它。
   */
  previewSingleStyle?: SingleValueStyleConfig;
  /** 面板模式把预览传送到这个节点。抽屉模式忽略。 */
  previewHost?: HTMLElement | null;
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
  surface?: OpsAnalysisWidgetSurface;
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
export type FilterValue =
  | string
  | number
  | Array<string | number>
  | TimeRangeValue
  | DateRangeValue
  | null;

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
  type: 'timeRange' | 'dateRange' | 'string' | 'number'; // 参数类型，用于绑定匹配；列表传参由 inputConfig.multiple 表达
  defaultValue?: FilterValue; // 默认值
  order: number; // 显示顺序
  enabled: boolean; // 是否启用
  inputMode?: 'input' | 'select' | 'radio' | 'organization'; // 兼容只读；新保存走 inputConfig.control
  /**
   * 旧字段：手动下拉选项（仅 inputMode 为 select/radio 时有效）。
   * 读取时由 normalizeInputConfig 自动按 static 模式处理。
   */
  options?: FilterOption[];
  inputConfig?: InputControlConfig;
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
  type: 'string' | 'timeRange' | 'dateRange' | 'number';
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
