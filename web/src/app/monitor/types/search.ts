export interface InstanceItem {
  instance_id: string;
  instance_name: string;
  instance_id_values: string[];
}

export interface SearchTableDataItem {
  metric: Record<string, string>;
  value: string;
  index: number;
  [key: string]: any;
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
}
