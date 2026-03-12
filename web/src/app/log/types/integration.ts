import React from 'react';

export interface CollectTypeItem {
  id: number;
  name: string;
  collector: string;
  icon?: string;
  domain?: string;
  display_description?: string;
  description: string;
  display_name?: string;
  display_collector?: string;
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

export interface IntegrationLogInstance {
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
  server?: any;
  host?: string | null;
  port?: string | null;
  jmx_url?: string | null;
  ENV_PORT?: string | null;
  ENV_HOST?: string | null;
  [key: string]: any;
}

export interface InstanceInfo {
  organizations?: (string | number)[];
  organization?: (string | number)[];
  instance_name?: string;
  instance_id?: string;
  id?: React.Key;
  name?: string;
  keys?: React.Key[];
}

export interface GroupInfo {
  organizations?: React.Key[];
  collect_type_id?: React.Key;
  id?: React.Key;
  rule?: GroupRule;
  name?: string;
  [key: string]: any;
}

export interface GroupRule {
  mode: string;
  conditions: FilterItem[];
}

export interface FilterItem {
  func?: string | null;
  field: string | null;
  op: string | null;
  value: string;
}
