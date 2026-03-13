// 搜索过滤器类型
type SearchFilters = Record<
  string,
  Array<{ lookup_expr: string; value: string | string[] | boolean }>
>;

// 字段配置格式，支持lookup_expr
interface FieldConfig {
  name: string; // 字段名，如 'operating_system', 'ip'
  label: string; // 显示标签
  lookup_expr: 'in' | 'icontains' | 'bool' | string; // 查询类型，支持扩展
  value?: string[] | string | boolean; // 默认值，in类型是数组，icontains是字符串，boolean是布尔
  options?: Array<{ id: string; name: string }>; // in类型才有options
}

interface SearchCombinationProps {
  className?: string;
  fieldConfigs?: FieldConfig[];
  fieldWidth?: number;
  selectWidth?: number;
  onChange?: (filters: SearchFilters) => void;
}

export type {
  SearchCombinationProps,
  FieldConfig,
  SearchFilters,
};
