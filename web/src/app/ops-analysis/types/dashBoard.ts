import { TopologyNodeData } from './topology';
export type FilterType = 'selector' | 'fixed';

export interface DataSourceParam {
  name: string;
  type: string;
  value: any;
  alias_name: string;
  filterType: 'params' | 'fixed' | 'filter';
}

export interface WidgetConfig {
  name?: string;
  chartType?: string;
  dataSource?: string | number;
  params?: { [key: string]: any };
  dataSourceParams?: any[];
}

export interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  name: string;
  description?: string;
  valueConfig?: WidgetConfig;
}

export type ViewConfigItem = LayoutItem | TopologyNodeData;

export interface ViewConfigProps {
  open: boolean;
  item: ViewConfigItem;
  onConfirm?: (values: any) => void;
  onClose?: () => void;
}

export interface ComponentSelectorProps {
  visible: boolean;
  onCancel: () => void;
  onOpenConfig?: (item: any) => void;
}

export interface BaseWidgetProps {
  config?: any;
  globalTimeRange?: any;
  refreshKey?: number;
  onDataChange?: (data: any) => void;
  onReady?: (hasData?: boolean) => void;
}

export interface WidgetMeta {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  defaultConfig?: any;
}

export interface WidgetDefinition {
  meta: WidgetMeta;
  configComponent?: React.ComponentType<any>;
}