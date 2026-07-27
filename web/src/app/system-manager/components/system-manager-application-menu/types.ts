export interface SourceMenuNode {
  name: string;
  display_name: string;
  url: string;
  icon?: string;
  type: 'menu' | 'page';
  tour?: {
    title: string;
    description: string;
    cover?: string;
    target: string;
    order: number;
  };
  isDetailMode?: boolean;
  hiddenChildren?: SourceMenuNode[];
  children?: SourceMenuNode[];
}

export interface FunctionMenuItem {
  id?: number;
  name: string;
  display_name: string;
  url: string;
  icon?: string;
  type: 'menu' | 'page';
  tour?: {
    title: string;
    description: string;
    cover?: string;
    target: string;
    order: number;
  };
  isExisting?: boolean;
  originName?: string;
  isDetailMode?: boolean;
  hiddenChildren?: SourceMenuNode[];
}
