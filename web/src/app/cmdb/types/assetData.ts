import {
  AttrFieldType,
  ModelItem,
  UserItem,
  AssoTypeItem,
  AssoFieldType,
  ColumnItem
} from '@/app/cmdb/types/assetManage';
  

export interface TopoData {
  src_result?: NodeData;
  dst_result?: NodeData;
}
  
export interface NodeData {
  _id: number;
  model_id: string;
  inst_name: string;
  asst_id?: string;
  expanded?: boolean;
  children: NodeData[];
}

export interface RecordsEnum {
  [key: string]: string;
}

export interface RecordItemList {
  type: string;
  created_at: string;
  operator: string;
  id: number;
  [key: string]: unknown;
}

export interface RecordItem {
  date: string;
  list: RecordItemList[];
}

export interface detailRef {
  showModal: (config: {
    subTitle: string;
    title: string;
    recordRow: any;
  }) => void;
}

export interface RecordDetailProps {
  userList: Array<any>;
  propertyList: AttrFieldType[];
  modelList: ModelItem[];
  enumList: RecordsEnum;
  connectTypeList: Array<AssoTypeItem>;
}

export interface FieldConfig {
  subTitle: string;
  title: string;
  recordRow: any;
}

export interface AssoListProps {
  userList: UserItem[];
  modelList: ModelItem[]; 
  assoTypeList: AssoTypeItem[];
}

export interface SelectInstanceProps {
  userList: UserItem[];
  models: ModelItem[];
  assoTypes: AssoTypeItem[];
  needFetchAssoInstIds?: boolean;
  onSuccess?: () => void;
}

export interface AssoTopoProps {
  modelList: ModelItem[];
  assoTypeList: AssoTypeItem[];
  modelId: string;
  instId: string;
}

export interface TopoDataProps {
  modelId: string;
  instId: string;
  topoData: TopoData;
  modelList: ModelItem[];
  assoTypeList: AssoTypeItem[];
}

export interface FieldModalRef {
  showModal: (info: FieldConfig) => void;
}

export interface SearchFilterProps {
  attrList: AttrFieldType[];
  proxyOptions: { proxy_id: string; proxy_name: string }[];
  userList: UserItem[];
  showExactSearch?: boolean;
  onSearch: (condition: unknown, value: any) => void;
}

export interface RelationItem extends AssoFieldType {
  name: string;
  relation_key: string;
}

export interface ExportModalProps {
  userList: any[];
  models: ModelItem[];
  assoTypes: AssoTypeItem[];
}

export interface ExportModalConfig {
  title: string;
  modelId: string;
  columns: ColumnItem[];
  selectedKeys: string[];
  exportType: 'selected' | 'currentPage' | 'all';
  tableData?: any[];
}

export interface ExportModalRef {
  showModal: (config: ExportModalConfig) => void;
}
