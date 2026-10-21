import { FilterItem } from '@/app/monitor/types';

export interface MultiThresholdField {
  level?: string;
  method: string;
  value: number | null;
}

export interface MetricExpressionRow {
  ref: string;
  metricId: number | null;
  metricName?: string;
  metricLabel?: string;
  filters: FilterItem[];
  groupAlgorithm: string;
  groupBy: string[];
  algorithm?: string;
  metricUnit?: string;
  calculationUnit?: string;
  thresholdUnit?: string;
  role?: 'level' | 'gate';
  threshold?: MultiThresholdField[];
  countPredicate?: { method?: string; value?: number | null };
  source?: 'metric' | 'formula';
  expression?: string;
  resultName?: string;
  operands?: MetricExpressionRow[];
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

export interface MultiQueryCondition {
  type: 'multi';
  result_name: string;
  combinator: 'all';
  queries: Array<{
    ref: string;
    source?: 'metric' | 'formula';
    metric_id?: number | null;
    metric_name?: string;
    expression?: string;
    filter?: FilterItem[];
    group_algorithm?: string;
    group_by: string[];
    algorithm: string;
    metric_unit: string;
    calculation_unit: string;
    threshold_unit: string;
    role: 'level' | 'gate';
    threshold: MultiThresholdField[];
    count_predicate?: { method?: string; value?: number | null };
    operands?: Array<{
      ref: string;
      metric_id?: number | null;
      metric_name?: string;
      filter?: FilterItem[];
      group_algorithm: string;
      group_by: string[];
    }>;
  }>;
}

export type MetricExpressionQueryCondition =
  | MetricQueryCondition
  | FormulaQueryCondition
  | MultiQueryCondition;
