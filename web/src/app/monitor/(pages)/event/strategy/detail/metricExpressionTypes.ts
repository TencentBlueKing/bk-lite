import { FilterItem } from '@/app/monitor/types';

export interface MetricExpressionRow {
  ref: string;
  metricId: number | null;
  metricName?: string;
  filters: FilterItem[];
  groupAlgorithm: string;
  groupBy: string[];
}

export interface MetricQueryCondition {
  type: 'metric';
  metric_id?: number;
  metric_name?: string;
  filter?: FilterItem[];
}

export interface FormulaQueryCondition {
  type: 'formula';
  result_name: string;
  expression: string;
  queries: Array<{
    ref: string;
    metric_id?: number;
    metric_name?: string;
    filter?: FilterItem[];
    group_algorithm: string;
    group_by: string[];
  }>;
}

export type MetricExpressionQueryCondition =
  | MetricQueryCondition
  | FormulaQueryCondition;
