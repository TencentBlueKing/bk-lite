import { DirItem } from './index';

export interface DiagramData {
  title: string;
  version?: string;
  description?: string;
  icons: any[];
  colors: any[];
  items: any[];
  views: any[];
  fitToScreen?: boolean;
}
export interface ArchitectureProps {
  selectedArchitecture?: DirItem | null;
}