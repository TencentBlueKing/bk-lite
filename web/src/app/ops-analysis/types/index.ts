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
}

export interface SidebarProps {
  onSelect?: (type: DirectoryType, itemInfo?: DirItem) => void;
  onDataUpdate?: (updatedItem: DirItem) => void;
}

export interface SidebarRef {
  clearSelection: () => void;
  setSelectedKeys: (keys: React.Key[]) => void;
}