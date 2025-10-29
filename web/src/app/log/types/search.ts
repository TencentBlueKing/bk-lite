import { TableDataItem } from '@/app/log/types';
import React from 'react';

export interface SearchTableProps {
  dataSource: TableDataItem[];
  fields: string[];
  loading?: boolean;
  scroll?: {
    x?: string | number;
    y?: string | number;
  };
  addToQuery: (row: TableDataItem, type: string) => void;
  onLoadMore?: () => void;
}

export interface SearchParams {
  query?: string;
  start_time?: string;
  end_time?: string;
  field?: string;
  fields_limit?: number;
  step?: string;
  limit?: number | null;
  log_groups?: React.Key[];
}

export interface LogStream {
  fields: {
    _stream: string;
  };
  timestamps: string[];
  values: number[];
  total: number;
}

export interface DetailItem {
  stream: string;
  value: number;
}

export interface AggregatedResult {
  time: React.Key;
  value: number;
  detail: DetailItem[];
}

export interface LogTerminalProps {
  className?: string;
  query: SearchParams;
  fetchData?: (loading: boolean) => void;
}

export interface LogTerminalRef {
  startLogStream: () => void;
}

export interface FieldListProps {
  loading?: boolean;
  className?: string;
  style?: Record<string, string>;
  fields: string[];
  addToQuery: (row: TableDataItem, type: string) => void;
  changeDisplayColumns: (columns: string[]) => void;
}

export interface Conidtion {
  query: string;
  log_groups: React.Key[];
  time_range: Record<string, number | string>;
}
export interface StoreConditions {
  name?: string;
  condition?: Conidtion;
}

export interface SearchConfig {
  times?: number[];
  logGroups?: React.Key[];
  text?: string;
}
