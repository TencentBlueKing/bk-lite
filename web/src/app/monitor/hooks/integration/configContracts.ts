import type { ReactNode } from 'react';

import type { TableDataItem } from '@/app/monitor/types';

export interface DashboardDisplayItem extends Record<string, unknown> {
  indexId: string;
  displayDimension?: string[];
}

export type DashboardDisplayEntry = string | DashboardDisplayItem;

export const normalizeDashboardDisplay = (
  items: DashboardDisplayEntry[] | undefined
): DashboardDisplayItem[] =>
  (items || []).map((item) =>
    typeof item === 'string'
      ? {
        indexId: item,
        displayDimension: []
      }
      : item
  );

export interface PluginConfigRequest {
  objectName: string;
  mode: 'manual';
  pluginName: string;
  dataSource?: TableDataItem[];
  onTableDataChange?: (data: TableDataItem[]) => void;
}

export interface ManualMonitorInstanceIdentity {
  instance_id: string | number;
  instance_name: string;
}

export interface ResolvedPluginConfig {
  collect_type: string;
  config_type: unknown[];
  collector: string;
  instance_type: string;
  object_name: string;
  formItems: ReactNode;
  initTableItems: TableDataItem;
  defaultForm: TableDataItem;
  columns: unknown[];
  getParams: (data: TableDataItem) => ManualMonitorInstanceIdentity;
  getConfigText: (data: TableDataItem) => string;
  getDefaultForm: (data: TableDataItem) => TableDataItem;
  configText: string;
}

export type PluginConfigExtension = Partial<ResolvedPluginConfig>;

export interface ObjectConfig {
  instance_type?: string;
  collectTypes?: Record<string, string>;
  groupIds?: { list?: string[]; default?: string[] };
  dashboardDisplay?: DashboardDisplayEntry[];
  plugins?: Record<
    string,
    {
      getPluginCfg?: (
        data: PluginConfigRequest
      ) => PluginConfigExtension | undefined;
    }
  >;
}

export type ObjectConfigFactory = () => ObjectConfig;

export const buildDefaultManualPluginConfig = (): ResolvedPluginConfig => ({
  collect_type: '',
  config_type: [],
  collector: '',
  instance_type: '',
  object_name: '',
  formItems: null,
  initTableItems: {},
  defaultForm: {},
  columns: [],
  getParams: () => ({
    instance_id: '',
    instance_name: ''
  }),
  getConfigText: () => '',
  getDefaultForm: () => ({}),
  configText: ''
});

export const resolvePluginConfig = (
  extension?: PluginConfigExtension
): ResolvedPluginConfig => ({
  ...buildDefaultManualPluginConfig(),
  ...extension
});
