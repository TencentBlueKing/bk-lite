import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';

export type DirectoryType = 'directory' | CanvasType | 'settings';
export type CreateDirectoryType = 'directory' | CanvasType;
export type ModalAction = 'addRoot' | 'addChild' | 'edit';

export interface DirItem {
  id: string;
  data_id: string; 
  name: string;
  type: DirectoryType;
  children?: DirItem[];
  desc?: string;
  groups?: number[];
  is_build_in?: boolean;
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
  parent?: number | null;
  groups?: number[];
  view_sets?: unknown;
}

export interface IconWithSize {
  width?: number;
  height?: number;
  size?: number;
}
