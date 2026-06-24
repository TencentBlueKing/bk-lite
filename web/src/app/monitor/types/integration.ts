import { MetricItem } from '@/app/monitor/types';
import React from 'react';

export interface OrderParam {
  id: number;
  sort_order: number;
  [key: string]: any;
}

export interface IntegrationMonitoredObject {
  key?: string;
  node_ids?: string | string[] | null;
  instance_name?: string | null;
  group_ids?: string[];
  url?: string | null;
  urls?: string | string[] | null;
  ip?: string | null;
  instance_id?: string;
  instance_type?: string;
  endpoint?: string | null;
  server?: string | null;
  host?: string | null;
  port?: string | null;
  jmx_url?: string | null;
  ENV_PORT?: string | null;
  ENV_HOST?: string | null;
  [key: string]: any;
}

export interface NodeConfigParam {
  configs?: any;
  collect_type?: string;
  monitor_object_id?: number;
  instances?: Omit<IntegrationMonitoredObject, 'key'>[];
}

export interface MetricInfo {
  type?: string;
  name?: string;
  display_name?: string;
  metric_group?: number;
  monitor_object?: number;
  instance_id_keys?: string[];
  id?: number;
  query?: string;
  data_type?: string;
  unit?: string;
  description?: string;
  dimensions?: string[];
}

export interface FilterItem {
  name: string | null;
  method: string | null;
  value: string;
}

export interface GroupingRules {
  type?: string;
  metric_id?: number;
  filter?: FilterItem[];
}

export interface RuleInfo {
  type?: string;
  name?: string;
  rule?: GroupingRules;
  organizations?: string[];
  monitor_object?: number;
  metric?: number;
  id?: number;
}

export interface InstanceInfo {
  organizations?: (string | number)[];
  organization?: (string | number)[];
  instance_name?: string;
  instance_id?: string;
  name?: string;
  keys?: React.Key[];
}

export interface ObjectInstItem {
  instance_id: string;
  agent_id: string;
  organizations: string[];
  time: string;
  [key: string]: unknown;
}

export interface MetricListItem {
  id: string;
  name: string;
  child: MetricItem[];
  display_name?: string;
  isOpen?: boolean;
  is_pre: boolean;
}

export interface DimensionItem {
  name: string;
  [key: string]: unknown;
}

export interface EnumItem {
  name: string | null;
  id: number | null;
  [key: string]: unknown;
}

export interface IntegrationAccessProps {
  showInterval?: boolean;
}

export interface InstNameConfig {
  index: number;
  field: string;
  dataIndex?: string;
}

export interface PluginItem {
  name: string;
  plugin_id?: number;
  template_id?: string;
  template_type?: string;
  is_custom?: boolean;
  display_description?: string;
  collector: string;
  collect_type: string;
  status: string;
  collect_mode: string;
  configured?: boolean;
  config_source?: 'configured' | 'reported_only' | 'configured_reported';
  time: string;
  config_ids?: string[];
}

export interface TemplateAccessGuideMetricItem {
  name: string;
  display_name?: string;
  description?: string;
  unit?: string;
  data_type?: string;
  dimensions?: any[];
}

export interface TemplateAccessGuideInstanceIdDimensionItem {
  key: string;
  required: boolean;
  description: string;
}

export interface TemplateAccessGuideDoc {
  template_id: string;
  display_name: string;
  plugin_id: number;
  description: string;
  metrics: TemplateAccessGuideMetricItem[];
  organization_id: number;
  cloud_region_id: number;
  monitor_object_id: number;
  instance_type: string;
  monitor_object_name: string;
  instance_id_keys: string[];
  endpoint: string;
  line_protocol_example: string;
  line_protocol_example_without_timestamp: string;
  line_protocol_example_with_timestamp_ms: string;
}

export interface FlowAccessGuideDoc {
  protocol: FlowProtocol;
  endpoint: string;
  endpoint_protocol?: string;
  listener_endpoints?: {
    protocol: string;
    protocol_name: string;
    endpoint: string;
    port: number;
  }[];
  has_multiple_listener_endpoints?: boolean;
  sampling_rule: string;
}

export type FlowProtocol = 'netflow' | 'sflow';

export interface FlowGuideParams {
  protocol: FlowProtocol;
  cloud_region_id: number;
  monitor_object_id: number;
}

export interface FlowDetectParams {
  instance_id: string;
  protocol: FlowProtocol;
  monitor_object_id: number;
}

export interface FlowAssetPayload {
  protocol: FlowProtocol;
  monitor_object_id: number;
  cloud_region_id: number;
  ip: string;
  name: string;
  fallback_sampling_rate: number;
  organizations: React.Key[];
  instance_id?: string;
}

export interface FlowIntegrationApi {
  createFlowAsset: (data: FlowAssetPayload) => Promise<any>;
  updateFlowAsset: (
    data: Partial<FlowAssetPayload> & { instance_id: string }
  ) => Promise<any>;
  getFlowGuide: (params: FlowGuideParams) => Promise<FlowAccessGuideDoc>;
  detectFlowStatus: (data: FlowDetectParams) => Promise<any>;
  [key: string]: unknown;
}

export interface SnmpCollectTemplateDoc {
  plugin_id: number;
  template_id?: string;
  display_name: string;
  content: string;
  type: string;
  config_type: string;
  file_type: string;
}

export interface ConfigItem {
  id: number;
  collect_type: string;
  config_type?: string;
  agent_id: string;
  status: string;
  time: number;
  config_content?: any;
  config_id: string;
  config_ids?: string[];
}

export interface ShowModalParams {
  instanceName: string;
  instanceId: number;
  selectedConfigId?: string;
  monitorObjId?: React.Key;
  objName: string;
  plugins?: PluginItem[];
  showTemplateList?: boolean;
}

export interface TemplateDrawerRef {
  showModal: (params: ShowModalParams) => void;
}

export interface K8sCommandData {
  command?: string;
  monitor_object_id?: number;
  instance_id?: string;
  cloud_region_id?: number;
  interval?: number;
}

export interface AccessConfigProps {
  onNext: (data?: any) => void;
  commandData?: K8sCommandData;
}

export interface CollectorInstallProps {
  onNext: () => void;
  onPrev: () => void;
  commandData?: K8sCommandData;
}

export interface AccessCompleteProps {
  onReset: () => void;
}
