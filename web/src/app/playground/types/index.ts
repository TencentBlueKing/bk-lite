import type { MenuProps } from 'antd';
import { JSX } from 'react';

export interface Option {
  label: string;
  value: string | number;
}

export interface Pagination {
  current: number;
  total: number;
  pageSize: number;
}

export interface EntityListProps<T> {
  data: T[];
  loading: boolean;
  searchSize?: 'large' | 'middle' | 'small';
  singleActionType?: 'button' | 'icon';
  filterOptions?: Option[];
  filter?: boolean;
  filterLoading?: boolean;
  operateSection?: React.ReactNode;
  infoText?: string | ((data: any) => string);
  menuActions?: (item: T) => MenuProps['items'];
  singleAction?: (item: T) => { text: string, onClick: (item: T) => void };
  openModal?: (item?: T) => void;
  onSearch?: (value: string) => void;
  onCardClick?: (item: T) => void;
  changeFilter?: (value: string[]) => void;
}

export interface TourItem {
  title: string;
  description: string;
  cover?: string;
  target: string;
  mask?: any;
  order: number;
}

export interface MenuItem {
  name: string;
  display_name?: string;
  url: string;
  icon: string;
  title: string;
  operation: string[];
  tour?: TourItem;
  isNotMenuItem?: boolean;
  children?: MenuItem[];
}

export interface ColumnItem {
  title: string;
  dataIndex: string;
  key: string;
  render?: (_: unknown, record: any) => JSX.Element;
  [key: string]: unknown;
}

export interface GroupFieldItem {
  title: string;
  key: string;
  child: ColumnItem[];
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

export interface ListItem {
  title?: string;
  label?: string;
  name?: string;
  display_name?: string;
  id?: string | number;
  value?: string | number;
}

export interface TabItem {
  key: string;
  label: string;
  name?: string;
  children?: JSX.Element | string;
}

export interface ChartData {
  timestamp: number;
  value1?: number;
  value2?: number;
  details?: Record<string, any>;
  [key: string]: unknown;
}

export interface TableDataItem {
  id?: number | string;
  [key: string]: any;
}

export interface ThresholdField {
  level: string;
  method: string;
  value: number | null;
}

export interface LevelMap {
  critical: string;
  error: string;
  warning: string;
  [key: string]: unknown;
}


//调用弹窗的类型
export interface ModalRef {
  showModal: (config: ModalConfig) => void;
}

export interface UserProfile {
  id: string,
  first_name: string,
  last_name: string
}

//调用弹窗接口传入的类型
export interface ModalConfig {
  type: string;
  title?: string;
  form?: any;
  key?: string;
  ids?: string[];
  selectedsystem?: string;
  nodes?: string[];
}

//调用弹窗的类型
export interface ModalRef {
  showModal: (config: ModalConfig) => void;
}

export interface UserProfile {
  id: string,
  first_name: string,
  last_name: string
}

export interface Pagination {
  current: number;
  total: number;
  pageSize: number;
}

export interface TableData {
  id: number,
  name: string,
  anomaly?: number,
  [key: string]: any
}