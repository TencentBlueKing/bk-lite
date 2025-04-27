import { Dayjs } from 'dayjs';
export interface TimeSelectorDefaultValue {
  selectValue: number | null;
  rangePickerVaule: [Dayjs, Dayjs] | null;
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

export interface ListItem {
  title?: string;
  label?: string;
  name?: string;
  id?: string | number;
  value?: string | number;
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
}

export interface UserInfoContextType {
  loading: boolean;
  roles: string[];
  groups: Group[];
  selectedGroup: Group | null;
  flatGroups: Group[];
  isSuperUser: boolean;
  isFirstLogin: boolean;
  userId: string;
  setSelectedGroup: (group: Group) => void;
}

export interface ClientData {
  id: string;
  name: string;
  client_id: string;
  description: string;
  url: string;
  icon?: string;
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
  operateSection?: React.ReactNode;
  infoText?: string;
  menuActions?: (item: T) => React.ReactNode;
  singleAction?: (item: T) => { text: string, onClick: (item: T) => void };
  openModal?: (item?: T) => void;
  onSearch?: (value: string) => void;
  onCardClick?: (item: T) => void;
  changeFilter?: (value: string[]) => void;
}
