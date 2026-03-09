import React from 'react';
import { MetricItem, ObjectItem, ChartData } from './index';

export interface InstanceItem {
  instance_id: string;
  instance_name: string;
  instance_id_values: string[];
}

export interface ConditionItem {
  label: string | null;
  condition: string | null;
  value: string;
}

export interface SearchParams {
  time?: number;
  end?: number;
  start?: number;
  step?: number;
  query: string;
  source_unit?: string;
}

export interface QueryGroup {
  id: string;
  name: string;
  object: React.Key;
  instanceIds: string[];
  metric: string | null;
  aggregation: string;
  conditions: ConditionItem[];
  collapsed: boolean;
}

export interface SearchPayload {
  queryGroups: QueryGroup[];
  activeGroup: QueryGroup;
  metricsMap: Record<string, MetricItem[]>;
  instancesMap: Record<string, InstanceItem[]>;
  objectsMap: Record<string, ObjectItem>;
}

export interface QueryPanelRef {
  getSearchPayload: () => SearchPayload | null;
  canSearch: () => boolean;
  getActiveGroup: () => QueryGroup;
}

export interface QueryPanelProps {
  onSearch: (payload: SearchPayload) => void;
}

export interface ChartItem {
  groupId: string;
  groupName: string;
  metric: MetricItem | null;
  data: ChartData[];
  unit: string;
  loading: boolean;
  duration: number;
  objectName: string;
  aggregation: string;
}

export interface ConditionItemData {
  label: string | null;
  condition: string | null;
  value: string;
}

export interface QueryGroupData {
  id: string;
  name: string;
  object: React.Key;
  instance_ids: string[];
  metric: string | null;
  aggregation: string;
  conditions: ConditionItemData[];
}

export interface SaveConditionParams {
  name: string;
  condition: QueryGroupData[];
  organizations?: number[];
  monitor_object_id?: React.Key | null;
  description?: string;
}

export interface ListConditionParams {
  name?: string;
  is_active?: boolean;
  monitor_object_id?: React.Key;
  page?: number;
  page_size?: number;
}

export interface SavedConditionItem {
  id: number;
  name: string;
  condition: QueryGroupData[];
  created_at: string;
  updated_at: string;
}

export interface SaveQueryModalRef {
  showModal: (queryGroups: QueryGroup[]) => void;
}

export interface SaveQueryModalProps {
  onSuccess?: () => void;
}

export interface SavedQueryDrawerRef {
  showDrawer: () => void;
}

export interface SavedQueryDrawerProps {
  onLoad: (queryGroups: QueryGroup[]) => void;
}
