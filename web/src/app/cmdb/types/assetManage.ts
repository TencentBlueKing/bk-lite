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
  modelForm: any;
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
  option: Array<EnumList>;
  attr_group?: string;
  isEdit?: boolean;
  children?: AttrFieldType[];
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
  render?: (_: unknown, record: any) => JSX.Element;
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
  organizationList: Organization[];
  instDetail: InstDetail;
  onsuccessEdit: () => void;
}

export interface InstDetail {
  inst_name?: string;
  organization?: string;
  [key: string]: unknown;
}

export interface EnumList {
  id: string | number;
  name: string;
}

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
  children: JSX.Element;
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
  children: JSX.Element;
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
    attrList: AttrFieldType[];
    formInfo: any;
    subTitle: string;
    title: string;
    model_id: string;
    list: Array<any>;
}

export interface FieldModalRef {
    showModal: (config: FieldConfig) => void;
}


