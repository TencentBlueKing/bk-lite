import type {
  DashboardActionConfig,
  FilterBindings,
  TableColumnConfigItem,
  TableConfig,
  TableFilterFieldConfig,
  ValueConfig,
  WidgetConfig,
  RuntimeParamControl,
} from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import type { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';
import type { NetworkStatusTopologyConfig } from '@/app/ops-analysis/types/sceneWidget';
import { validateRuntimeParamControl } from '@/app/ops-analysis/utils/runtimeParamControl';

export interface WidgetConfigFormValues {
  name: string;
  description?: string;
  chartType: string;
  sceneWidgetType?: 'networkStatusTopology';
  networkStatusTopology?: NetworkStatusTopologyConfig;
  chartThemeMode?: OpsChartThemeMode;
  dataSource?: string | number;
  compare?: boolean;
  dataSourceParams?: ParamItem[];
  params?: Record<string, string | number | boolean | [number, number] | null>;
  tableConfig?: TableConfig;
  selectedFields?: string[];
  topNLabelField?: string;
  topNValueField?: string;
  runtimeParamControlEnabled?: boolean;
  runtimeParamControl?: RuntimeParamControl;
  unit?: string;
  unitId?: string;
  valueMappings?: ValueConfig['valueMappings'];
  conversionFactor?: number;
  decimalPlaces?: number;
  gaugeMin?: number;
  gaugeMax?: number;
  gaugeShape?: 'semicircle' | 'circle';
  actions?: DashboardActionConfig[];
  appearance?: ValueConfig['appearance'];
}

type SubmitDisplayColumn = TableColumnConfigItem & {
  id: string;
  isDefault?: boolean;
};

type SubmitFilterField = TableFilterFieldConfig & {
  id: string;
};

export type WidgetSubmitError =
  | 'duplicateFieldKey'
  | 'atLeastOneVisibleColumn'
  | 'invalidRuntimeParamControl';

export interface BuildWidgetSubmitConfigInput {
  values: WidgetConfigFormValues;
  chartType: string;
  showChartThemeMode: boolean;
  showTableFilterFields: boolean;
  selectedFields: string[];
  thresholdColors: ThresholdColorConfig[];
  filterBindings: FilterBindings;
  displayColumns: SubmitDisplayColumn[];
  filterFields: SubmitFilterField[];
  actions: DashboardActionConfig[];
}

export interface BuildWidgetSubmitConfigResult {
  config?: WidgetConfig;
  error?: WidgetSubmitError;
}

const buildSceneWidgetConfig = (
  values: WidgetConfigFormValues,
): WidgetConfig => {
  const topologyConfig = values.networkStatusTopology;
  return {
    name: values.name,
    description: values.description,
    chartType: 'networkStatusTopology',
    sceneWidgetType: 'networkStatusTopology',
    networkStatusTopology: {
      modelId: topologyConfig?.modelId || '',
      instId: topologyConfig?.instId || '',
      depth: topologyConfig?.depth || 2,
    },
    appearance: values.appearance,
  };
};

const buildTableConfig = ({
  displayColumns,
  filterFields,
  showTableFilterFields,
}: Pick<
  BuildWidgetSubmitConfigInput,
  'displayColumns' | 'filterFields' | 'showTableFilterFields'
>): BuildWidgetSubmitConfigResult & { tableConfig?: TableConfig } => {
  const tableConfig: TableConfig = {};

  if (showTableFilterFields && filterFields.length > 0) {
    tableConfig.filterFields = filterFields
      .filter((field) => field.key)
      .map(({ key, label, inputType }) => ({
        key,
        label,
        inputType,
      }));
  }

  const validDisplayColumns = displayColumns
    .map((column) => ({
      ...column,
      key: column.key.trim(),
      title: column.title?.trim() || column.key.trim(),
    }))
    .filter((column) => column.key);

  const duplicateKeySet = new Set<string>();
  const hasDuplicateKeys = validDisplayColumns.some((column) => {
    if (duplicateKeySet.has(column.key)) return true;
    duplicateKeySet.add(column.key);
    return false;
  });

  if (hasDuplicateKeys) {
    return { error: 'duplicateFieldKey' };
  }

  const hasVisibleColumn = validDisplayColumns.some(
    (column) => column.visible !== false,
  );
  if (!hasVisibleColumn) {
    return { error: 'atLeastOneVisibleColumn' };
  }

  if (validDisplayColumns.length > 0) {
    tableConfig.columns = validDisplayColumns.map((column, index) => ({
      key: column.key,
      title: column.title,
      visible: column.visible,
      order: index,
      columnType: column.columnType,
    }));
  }

  return {
    tableConfig:
      tableConfig.filterFields?.length || tableConfig.columns?.length
        ? tableConfig
        : undefined,
  };
};

const applySingleValueConfig = (
  result: WidgetConfig,
  values: WidgetConfigFormValues,
  selectedFields: string[],
  thresholdColors: ThresholdColorConfig[],
) => {
  result.selectedFields = selectedFields;
  result.thresholdColors = thresholdColors;
  result.compare = !!values.compare;
  if (values.unit !== undefined) result.unit = values.unit;
  result.unitId = values.unitId || undefined;
  result.valueMappings = values.valueMappings || undefined;
  if (values.conversionFactor !== undefined) {
    result.conversionFactor = values.conversionFactor;
  }
  if (values.decimalPlaces !== undefined) {
    result.decimalPlaces = values.decimalPlaces;
  }
};

const applyGaugeConfig = (
  result: WidgetConfig,
  values: WidgetConfigFormValues,
  selectedFields: string[],
  thresholdColors: ThresholdColorConfig[],
) => {
  result.selectedFields = selectedFields;
  result.thresholdColors = thresholdColors;
  if (values.unit !== undefined) result.unit = values.unit;
  result.unitId = values.unitId || undefined;
  result.valueMappings = values.valueMappings || undefined;
  if (values.conversionFactor !== undefined) {
    result.conversionFactor = values.conversionFactor;
  }
  if (values.decimalPlaces !== undefined) {
    result.decimalPlaces = values.decimalPlaces;
  }
  if (values.gaugeMin !== undefined) result.gaugeMin = values.gaugeMin;
  if (values.gaugeMax !== undefined) result.gaugeMax = values.gaugeMax;
  if (values.gaugeShape !== undefined) result.gaugeShape = values.gaugeShape;
};

export const buildWidgetSubmitConfig = ({
  values,
  chartType,
  showChartThemeMode,
  showTableFilterFields,
  selectedFields,
  thresholdColors,
  filterBindings,
  displayColumns,
  filterFields,
  actions,
}: BuildWidgetSubmitConfigInput): BuildWidgetSubmitConfigResult => {
  if (values.sceneWidgetType === 'networkStatusTopology') {
    return { config: buildSceneWidgetConfig(values) };
  }

  const result: WidgetConfig = { ...values } as WidgetConfig;
  delete (result as WidgetConfig & {
    runtimeParamControlEnabled?: boolean;
  }).runtimeParamControlEnabled;

  if (chartType === 'table' || chartType === 'eventTable') {
    const tableResult = buildTableConfig({
      displayColumns,
      filterFields,
      showTableFilterFields,
    });
    if (tableResult.error) {
      return { error: tableResult.error };
    }
    if (tableResult.tableConfig) {
      result.tableConfig = tableResult.tableConfig;
    }
  }

  if (!showChartThemeMode) {
    delete result.chartThemeMode;
  } else if (result.chartThemeMode === 'default') {
    delete result.chartThemeMode;
  }

  if (chartType === 'table') {
    const displayColumnKeys = new Set(
      displayColumns.map((column) => (column.key || '').trim()).filter(Boolean),
    );
    const validActions = actions.filter((action) =>
      displayColumnKeys.has(action.columnKey),
    );
    if (validActions.length > 0) {
      result.actions = validActions;
    } else {
      delete result.actions;
    }
  }

  if (chartType === 'single') {
    applySingleValueConfig(result, values, selectedFields, thresholdColors);
  }

  if (chartType === 'gauge') {
    applyGaugeConfig(result, values, selectedFields, thresholdColors);
  }

  if (chartType === 'topN') {
    result.topNLabelField = values.topNLabelField;
    result.topNValueField = values.topNValueField;
    if (values.runtimeParamControlEnabled) {
      if (
        validateRuntimeParamControl(
          values.runtimeParamControl,
          values.dataSourceParams || [],
        )
      ) {
        return { error: 'invalidRuntimeParamControl' };
      }
      result.runtimeParamControl = values.runtimeParamControl;
    } else {
      delete result.runtimeParamControl;
    }
  } else {
    delete result.runtimeParamControl;
  }

  if (filterBindings && Object.keys(filterBindings).length > 0) {
    result.filterBindings = filterBindings;
  }

  return { config: result };
};
