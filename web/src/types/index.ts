import React from 'react';
import { Dayjs } from 'dayjs';
export interface TimeSelectorDefaultValue {
  selectValue: number | null;
  rangePickerVaule: [Dayjs, Dayjs] | null;
}

export interface ColumnItem {
  title: string;
  dataIndex: string;
  key: string;
  render?: (_: unknown, record: any) => React.ReactNode;
  [key: string]: unknown;
}

export interface GroupFieldItem {
  title: string;
  key: string;
  child: ColumnItem[];
}

export interface ListItem {
  title?: string;
  label?: string;
  name?: string;
  id?: string | number;
  value?: string | number;
  color?: string;
}

export interface groupProps {
  id: string;
  name: string;
  path: string;
}

export interface Group {
  id: string;
  name: string;
  children?: Group[];
  hasAuth?: boolean;
  parentId?: string;
  subGroupCount?: number;
  subGroups?: Group[];
}

export interface UserInfoContextType {
  loading: boolean;
  roles: string[];
  groups: Group[];
  groupTree: Group[];
  selectedGroup: Group | null;
  flatGroups: Group[];
  isSuperUser: boolean;
  isFirstLogin: boolean;
  userId: string;
  username: string;
  displayName: string;
  setSelectedGroup: (group: Group) => void;
  refreshUserInfo: () => Promise<void>;
}

export interface ClientData {
  id: string;
  name: string;
  display_name: string;
  description: string;
  url: string;
  icon?: string;
  is_build_in?: boolean;
  tags?: string[];
}

export interface AppConfigItem extends ClientData {
  index: number;
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
  iconNode?: React.ReactNode;
  title: string;
  operation: string[];
  tour?: TourItem;
  isDirectory?: boolean;
  isNotMenuItem?: boolean;
  hasDetail?: boolean;
  children?: MenuItem[];
  withParentPermission?: boolean;
}

export interface Option {
  label: string;
  value: string;
}

export interface EntityListProps<T> {
  data: T[];
  loading: boolean;
  searchSize?: 'large' | 'middle' | 'small';
  singleActionType?: 'button' | 'icon';
  filterOptions?: Option[];
  filter?: boolean;
  filterLoading?: boolean;
  search?: boolean;
  toolbarPrefix?: React.ReactNode;
  operateSection?: React.ReactNode;
  infoText?: string;
  nameField?: string;
  iconRender?: (icon: string) => React.ReactNode;
  descSlot?: (item: T) => React.ReactNode;
  showBuiltinTag?: boolean;
  menuActions?: (item: T) => React.ReactNode;
  singleAction?: (item: T) => { text: string; onClick: (item: T) => void };
  openModal?: (item?: T) => void;
  onSearch?: (value: string) => void;
  onCardClick?: (item: T) => void;
  changeFilter?: (value: string[]) => void;
  /** 自定义卡片渲染；传入后覆盖默认卡片壳（OpsPilot Look B 等） */
  renderCard?: (item: T) => React.ReactNode;
  /** 隐藏顶部工具条（由页面页头自行承载搜索/新建时使用） */
  hideToolbar?: boolean;
  /** 加载态自定义内容（如骨架屏）；未传则沿用居中 Spin */
  loadingContent?: React.ReactNode;
}

export interface TimeSelectorRef {
  getValue: () => number[] | null;
}

export interface HeatMapDataItem {
  event_time: string;
  [key: string]: any;
}
