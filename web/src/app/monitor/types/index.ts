import { Dayjs } from 'dayjs';

export interface ColumnItem {
  title: string;
  dataIndex: string;
  key: string;
  render?: (_: unknown, record: any) => JSX.Element;
  [key: string]: unknown;
}

export interface ListItem {
  title?: string;
  label?: string;
  name?: string;
  display_name?: string;
  id?: string | number;
  value?: string | number;
}

export interface ModalConfig {
  type: string;
  form: any;
  subTitle?: string;
  title: string;
  [key: string]: any;
}

export interface ModalRef {
  showModal: (config: ModalConfig) => void;
}

export interface CascaderItem {
  label: string;
  value: string | number;
  children: CascaderItem[];
}

export interface TreeItem {
  title: JSX.Element | string;
  key: string | number;
  label?: string;
  children: TreeItem[];
}

export interface UserItem {
  id: string;
  username: string;
  [key: string]: unknown;
}

export interface Organization {
  id: string;
  name: string;
  label?: string;
  value?: string;
  children: Array<SubGroupItem>;
  [key: string]: unknown;
}

export interface SubGroupItem {
  value?: string;
  label?: string;
  children?: Array<SubGroupItem>;
}

export interface OriginSubGroupItem {
  id: string;
  name: string;
  parentId: string;
  subGroupCount: number;
  subGroups: Array<OriginSubGroupItem>;
}
export interface OriginOrganization {
  id: string;
  name: string;
  subGroupCount: number;
  subGroups: Array<OriginSubGroupItem>;
  [key: string]: unknown;
}
export interface TabItem {
  key: string;
  label: string;
  name?: string;
  children?: JSX.Element | string;
}

export interface ChartData {
  time: number;
  value1?: number;
  value2?: number;
  details?: Record<string, any>;
  [key: string]: unknown;
}

export interface SegmentedItem {
  label: string;
  value: string;
}

export interface Pagination {
  current: number;
  total: number;
  pageSize: number;
}

export interface TableDataItem {
  id?: number | string;
  [key: string]: any;
}

export interface TimeSelectorDefaultValue {
  selectValue: number | null;
  rangePickerVaule: [Dayjs, Dayjs] | null;
}

export interface TimeLineItem {
  color: string;
  children: JSX.Element;
}

export interface ViewQueryKeyValuePairs {
  keys: string[];
  values: string[];
}

export interface ModalProps {
  onSuccess: () => void;
}

export interface HexagonData {
  name: string;
  description: React.ReactNode | string;
  fill: string;
}

export interface TimeValuesProps {
  timeRange: number[];
  originValue: number | null;
}

export interface InstanceParam {
  page?: number;
  page_size?: number;
  add_metrics?: boolean;
  name?: string;
  vm_params?: any;
}

export interface GroupInfo {
  name?: string;
  description?: string;
  id?: number;
}

export interface ObjectItem {
  id: number;
  name: string;
  type: string;
  plugin_name?: string;
  plugin_id?: number;
  display_description?: string;
  description: string;
  display_name?: string;
  display_type?: string;
  options?: ObjectItem[];
  label?: string;
  value?: string;
  [key: string]: unknown;
}

export interface IntegrationItem {
  label: string;
  value: string;
  list: ObjectItem[];
  name?: string;
  [key: string]: unknown;
}

export interface ChartProps {
  instance_id?: string;
  showInstName?: boolean;
  instance_id_keys: string[];
  instance_id_values: string[];
  instance_name: string;
  title: string;
  dimensions: any[];
  [key: string]: unknown;
}

export interface MetricItem {
  id: number;
  metric_group: number;
  metric_object: number;
  name: string;
  type: string;
  display_name?: string;
  display_description?: string;
  instance_id_keys?: string[];
  dimensions: any[];
  query?: string;
  unit?: string;
  displayType?: string;
  description?: string;
  viewData?: any[];
  style?: {
    width: string;
    height: string;
  };
  [key: string]: unknown;
}

export interface IndexViewItem {
  name?: string;
  display_name?: string;
  id: number;
  isLoading?: boolean;
  child?: any[];
}

export interface ThresholdField {
  level: string;
  method: string;
  value: number | null;
}

export interface FilterItem {
  name: string | null;
  method: string | null;
  value: string;
}

export interface ChartDataItem {
  metric: Record<string, string>;
  values: [number, string][];
  [key: string]: any;
}

export interface LevelMap {
  critical: string;
  error: string;
  warning: string;
  [key: string]: unknown;
}

export interface StateMap {
  new: string;
  recovered: string;
  closed: string;
  [key: string]: any;
}

export interface NodeWorkload {
  created_by_kind: string;
  created_by_name: string;
}

export interface TreeSortData {
  type: string;
  name_list: string[];
}

export interface ObjectIconMap {
  [key: string]: string;
}
