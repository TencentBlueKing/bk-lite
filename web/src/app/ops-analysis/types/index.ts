export type DirectoryType = 'directory' | 'dashboard' | 'topology' | 'architecture' | 'settings';
export type CreateDirectoryType = 'directory' | 'dashboard' | 'topology' | 'architecture';
export type ModalAction = 'addRoot' | 'addChild' | 'edit';

export interface DirItem {
  id: string;
  data_id: string; 
  name: string;
  type: DirectoryType;
  children?: DirItem[];
  desc?: string;
  groups?: number[];
}

export interface SidebarProps {
  onSelect?: (type: DirectoryType, itemInfo?: DirItem) => void;
  onDataUpdate?: (updatedItem: DirItem) => void;
}

export interface SidebarRef {
  clearSelection: () => void;
  setSelectedKeys: (keys: React.Key[]) => void;
}

export interface FormValues {
  name: string;
  desc?: string;
  groups?: number[];
}

export interface ItemData {
  name: string;
  desc?: string;
  directory?: number;
  parent_id?: number;
  groups?: number[];
}

export interface IconWithSize {
  width?: number;
  height?: number;
  size?: number;
}