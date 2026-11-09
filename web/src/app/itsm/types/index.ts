export interface FormFieldSchema {
  key: string;
  type: string;
  label: string;
  required?: boolean;
  default?: unknown;
  props?: Record<string, unknown>;
  source?: { type: string; options?: Array<{ label: string; value: string }> };
}

export interface FormSchema {
  version: number;
  fields: FormFieldSchema[];
}

export interface ConditionItem {
  field: string;
  op: string;
  value?: unknown;
}

export interface ConditionGroup {
  logic: 'and' | 'or';
  items: Array<ConditionItem | ConditionGroup>;
}

export interface FlowNodeData {
  label: string;
  nodeType: string;
}
