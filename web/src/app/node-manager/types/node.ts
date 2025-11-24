interface SearchValue {
  field: string;
  value: string;
}

// 搜索过滤器类型
type SearchFilters = Record<
  string,
  Array<{ lookup_expr: string; value: string | string[] }>
>;

// 新的字段配置格式，支持lookup_expr
interface FieldConfig {
  name: string; // 字段名，如 'operating_system', 'ip'
  label: string; // 显示标签
  lookup_expr: 'in' | 'icontains' | string; // 查询类型，支持扩展
  value?: string[] | string; // 默认值，in类型是数组，icontains是字符串
  options?: Array<{ id: string; name: string }>; // in类型才有options
}

interface SearchCombinationProps {
  className?: string;
  fieldConfigs?: FieldConfig[];
  fieldWidth?: number;
  selectWidth?: number;
  onChange?: (filters: SearchFilters) => void;
}

interface SearchTag {
  type: 'string' | 'enum';
  field: string;
  value: string;
  options?: Array<{ id: string; name: string }>;
}

export type {
  SearchValue,
  SearchCombinationProps,
  SearchTag,
  FieldConfig,
  SearchFilters,
};
