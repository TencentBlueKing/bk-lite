interface TableDataItem {
  id?: string | number;
  [key: string]: any;
}

//传入modal的参数类型成功的回调
interface ModalSuccess {
  onSuccess: (config?: any) => void;
  config?: any;
}

//调用弹窗接口传入的类型
interface ModalConfig {
  type: string;
  title?: string;
  form?: TableDataItem;
  key?: string;
  ids?: string[];
  selectedsystem?: string;
  nodes?: string[];
}

//调用弹窗的类型
interface ModalRef {
  showModal: (config: ModalConfig) => void;
}

interface TopSectionProps {
  width?: number;
  height?: number;
  title?: React.ReactNode;
  children: React.ReactNode;
}

//下拉配置
interface OptionItem {
  label: string;
  value: string | number;
  template?: string;
}

//云区域的卡片
interface Collectorcardprops {
  id: string;
  name: string;
  system: string[];
  introduction: string;
}

interface DropDownItem {
  key: string;
  label: string;
}

interface SegmentedItem {
  label: string;
  value: string;
}

interface Pagination {
  current: number;
  total: number;
  pageSize: number;
}

export type {
  TableDataItem,
  ModalSuccess,
  ModalRef,
  TopSectionProps,
  OptionItem,
  Collectorcardprops,
  DropDownItem,
  Pagination,
  SegmentedItem,
};
