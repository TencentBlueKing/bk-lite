import React from 'react';
import { Dayjs } from 'dayjs';

export interface ColumnItem {
  title: string;
  dataIndex: string;
  key: string;
  render?: (_: unknown, record: any) => React.ReactElement;
  [key: string]: unknown;
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
  title: React.ReactElement | string;
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
  children?: React.ReactElement | string;
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
  rangePickerValue: [Dayjs, Dayjs] | null;
}

export interface TimeLineItem {
  color: string;
  children: React.ReactElement;
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

export interface LevelItem {
    value: string | number;
    label: string;
    id: number;
    level_id: number;
    level_name: string;
    level_display_name: string;
    color: string;
    icon: string;
    description: string;
    level_type: string;
}

export interface CommonContextType {
    userList: UserItem[];
    levelList: LevelItem[];
    levelMap: Record<string, string>;
    levelListEvent: LevelItem[];
    levelMapEvent: Record<string, string>;
    levelListIncident: LevelItem[];
    levelMapIncident: Record<string, string>;
}
