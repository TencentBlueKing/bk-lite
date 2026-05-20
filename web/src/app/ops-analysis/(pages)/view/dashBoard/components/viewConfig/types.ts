import type { TableFilterFieldConfig, TableColumnConfigItem } from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';

export type DisplayColumnRow = TableColumnConfigItem & {
  id: string;
  isDefault?: boolean;
};

export type FilterFieldRow = TableFilterFieldConfig & { id: string };

export interface FormValues {
  name: string;
  description?: string;
  chartType: string;
  dataSource: string | number;
  dataSourceParams?: ParamItem[];
  params?: Record<string, string | number | boolean | [number, number] | null>;
  tableConfig?: import('@/app/ops-analysis/types/dashBoard').TableConfig;
  selectedFields?: string[];
  topNLabelField?: string;
  topNValueField?: string;
  unit?: string;
  conversionFactor?: number;
  decimalPlaces?: number;
}

export interface FilterFieldOption {
  label: string;
  value: string;
}

export interface TableConfigState {
  filterFields: FilterFieldRow[];
  displayColumns: DisplayColumnRow[];
  isProbingColumns: boolean;
  paramsChangedAfterProbe: boolean;
  displayColumnsError: string;
}

export interface TableConfigActions {
  setFilterFields: (fields: FilterFieldRow[]) => void;
  setDisplayColumns: (columns: DisplayColumnRow[]) => void;
  setIsProbingColumns: (value: boolean) => void;
  setParamsChangedAfterProbe: (value: boolean) => void;
  setDisplayColumnsError: (error: string) => void;
  handleAddFilterField: (index: number) => void;
  handleDeleteFilterField: (id: string) => void;
  handleFilterFieldChange: (
    id: string,
    fieldName: keyof TableFilterFieldConfig,
    value: string,
  ) => void;
  handleAddDisplayColumn: (index: number) => void;
  handleDeleteDisplayColumn: (id: string) => void;
  handleDisplayColumnChange: (
    id: string,
    fieldName: keyof TableColumnConfigItem,
    value: string | boolean,
  ) => void;
  handleDisplayColumnKeyBlur: (id: string) => void;
  handleDisplayColumnDragEnd: (targetTableData: DisplayColumnRow[]) => void;
  handleReProbeColumns: () => Promise<void>;
  createDefaultFilterField: () => FilterFieldRow;
  createDefaultDisplayColumn: () => DisplayColumnRow;
}

export interface SingleValueConfigState {
  singleValueTreeData: any[];
  selectedFields: string[];
  loadingSingleValueData: boolean;
  thresholdColors: import('@/app/ops-analysis/utils/thresholdUtils').ThresholdColorConfig[];
}

export interface SingleValueConfigActions {
  setSingleValueTreeData: (data: any[]) => void;
  setSelectedFields: (fields: string[]) => void;
  setLoadingSingleValueData: (loading: boolean) => void;
  setThresholdColors: React.Dispatch<
    React.SetStateAction<
      import('@/app/ops-analysis/utils/thresholdUtils').ThresholdColorConfig[]
    >
  >;
  handleThresholdChange: (
    index: number,
    field: 'value' | 'color',
    value: string | number,
  ) => void;
  handleThresholdBlur: (index: number, value: number | null) => void;
  addThreshold: (afterIndex?: number) => void;
  removeThreshold: (index: number) => void;
  fetchSingleValueDataFields: () => Promise<void>;
  handleSingleValueFieldChange: (checkedKeys: any) => void;
}

export interface FilterFieldColumnDeps {
  filterFieldOptions: FilterFieldOption[];
  filterInputTypeOptions: { label: string; value: string }[];
  t: (key: string) => string;
}

export interface DisplayColumnTableDeps {
  t: (key: string) => string;
}
