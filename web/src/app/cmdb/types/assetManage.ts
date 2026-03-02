import React from 'react';
export interface GroupItem {
  classification_name: string;
  classification_id: string;
  count: number;
  list: ModelItem[];
  [key: string]: any;
}

export interface ModelItem {
  model_id: string;
  classification_id: string;
  model_name: string;
  icn: string;
  organization?: number;
  group?: number | number[];
  [key: string]: any;
}

export interface GroupFieldType {
  classification_id?: string;
  classification_name?: string;
  _id?: string | number;
}

export interface GroupConfig {
  type: string;
  groupInfo: GroupFieldType;
  subTitle: string;
  title: string;
}

export interface ModelConfig {
  type: string;
  modelForm?: Partial<ModelItem>;
  subTitle: string;
  title: string;
}

export interface ClassificationItem {
  classification_name: string;
  classification_id: string;
  [key: string]: any;
}

export interface AssoTypeItem {
  asst_id: string;
  asst_name: string;
  [key: string]: any;
}

export interface AssoFieldType {
  asst_id: string;
  src_model_id: string;
  dst_model_id: string;
  mapping: string;
  _id?: string;
  [key: string]: unknown;
}

export interface AttrFieldType {
  model_id?: string;
  attr_id: string;
  attr_name: string;
  attr_type: string;
  is_only?: boolean;
  is_required: boolean;
  editable: boolean;
  option: AttrOption;
  attr_group?: string;
  isEdit?: boolean;
  children?: AttrFieldType[];
  user_prompt?: string;
  [key: string]: unknown;
}

export interface ModelIconItem {
  icn: string | undefined;
  model_id: string | undefined;
  [key: string]: unknown;
}
export interface ColumnItem {
  title: string;
  dataIndex: string;
  key: string;
  render?: (_: unknown, record: any) => React.ReactElement;
  [key: string]: any;
}
export interface UserItem {
  id: string;
  username: string;
  [key: string]: unknown;
}
export interface SubGroupItem {
  value?: string;
  label?: string;
  children?: Array<SubGroupItem>;
}
export interface Organization {
  id: string;
  name: string;
  value?: string;
  children: Array<SubGroupItem>;
  [key: string]: unknown;
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

export interface AssetDataFieldProps {
  propertyList: AttrFieldType[];
  userList: UserItem[];
  instDetail: InstDetail;
  onsuccessEdit: () => void;
}

export interface InstDetail {
  inst_name?: string;
  organization?: string;
  [permission: string]: any;
}

export interface EnumList {
  id: string | number;
  name: string;
}

// 字符串类型的 option
export interface StrAttrOption {
  validation_type: 'unrestricted' | 'ipv4' | 'ipv6' | 'email' | 'mobile_phone' | 'url' | 'json' | 'custom';
  custom_regex: string;
  widget_type: 'single_line' | 'multi_line';
}

// 时间类型的 option
export interface TimeAttrOption {
  display_format: 'datetime' | 'date';
}

// 数字类型的 option
export interface IntAttrOption {
  min_value: string | number;
  max_value: string | number;
}

export interface TableColumnSpec {
  column_id: string;
  column_name: string;
  column_type: 'str' | 'number';
  order: number;
}

export type TableAttrOption = TableColumnSpec[];

// 属性字段最小结构（用于工具函数）
export interface AttrLike {
  attr_type: string;
  option: unknown;
  is_required?: boolean;
}

// 属性 option 联合类型
export type AttrOption = EnumList[] | StrAttrOption | TimeAttrOption | IntAttrOption | TableAttrOption | Record<string, unknown>;

export interface CredentialListItem {
  classification_name: string;
  classification_id: string;
  list: CredentialChildItem[];
}

export interface CredentialChildItem {
  model_id: string;
  model_name: string;
  assoModelIds: string[];
  attrs: AttrFieldType[];
}

export interface AssoInstItem {
  key: string;
  label: string;
  model_asst_id: string;
  children: React.ReactElement;
  [key: string]: unknown;
}

export interface AssoDetailItem {
  asst_id: string;
  src_model_id: string;
  model_asst_id: string;
  dst_model_id: string;
  inst_list: InstDetail[];
  [key: string]: unknown;
}

export interface CrentialsAssoInstItem {
  key: string;
  label: string;
  children: React.ReactElement;
  inst_list: CrentialsAssoDetailItem[];
  [key: string]: unknown;
}

export interface CrentialsAssoDetailItem {
  credential_type: string;
  name?: string;
  _id?: number | string | undefined;
  inst_asst_id?: number | string | undefined;
  [key: string]: unknown;
}

export interface AssoListRef {
  expandAll: (isExpand: boolean) => void;
  showRelateModal: () => void;
}

export interface ListItem {
  name: string;
  id: string | number;
  [key: string]: unknown;
}

export interface RelationListInstItem {
  id: string | number | undefined;
  inst_asst_id: string | number | undefined;
}

export interface RelationInstanceConfig {
  model_id: string;
  list: RelationListInstItem[];
  title: string;
  instId: string;
}
export interface RelationInstanceRef {
  showModal: (config: RelationInstanceConfig) => void;
}

export interface FieldConfig {
  type: string;
  attrList: FullInfoGroupItem[]; // 属性列表，分组数据
  formInfo: any;
  subTitle: string;
  title: string;
  model_id: string;
  list: Array<any>;
}

export interface FieldModalRef {
  showModal: (config: FieldConfig) => void;
}

// 属性分组相关类型
export interface AttrGroup {
  id: number;
  model_id: string;
  group_name: string;
  order: number;
  is_collapsed: boolean;
  description: string;
  attr_orders: any[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AttrItem {
  attr_id: string;
  attr_name: string;
  attr_type: string;
  is_required: boolean;
  editable: boolean;
  is_only: boolean;
  group_id?: string;
  order?: number;
}

// 获取模型完整信息接口相关类型
export interface FullInfoAttrItem {
  attr_id: string;
  attr_name: string;
  attr_type: string;
  option: AttrOption;
  attr_group: string;
  is_only: boolean;
  editable: boolean;
  is_required: boolean;
  is_pre: boolean;
  user_prompt?: string;
  [key: string]: unknown;
}

export interface FullInfoGroupItem {
  id: number;
  group_name: string;
  order: number;
  is_collapsed: boolean;
  description: string;
  attrs: FullInfoAttrItem[];
  attrs_count: number;
  can_move_up: boolean;
  can_move_down: boolean;
  can_delete: boolean;
}

export interface ModelFullInfo {
  model_id: string;
  model_name: string;
  groups: FullInfoGroupItem[];
  total_groups: number;
  total_attrs: number;
}

export interface ModelFullInfoResponse {
  data: ModelFullInfo;
  result: boolean;
  message: string;
}
