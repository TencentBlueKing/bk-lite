import type {
  CardListConfig,
  DashboardActionConfig,
  FilterBindings,
  TableColumnConfigItem,
  TableConfig,
  TableFilterFieldConfig,
  ValueConfig,
  WidgetConfig,
} from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import {
  isFiniteNumber,
  type ThresholdColorConfig,
} from '@/app/ops-analysis/utils/thresholdUtils';
import type {
  NetworkStatusTopologyConfig,
  SceneWidgetType,
} from '@/app/ops-analysis/types/sceneWidget';
import {
  normalizeCardListAccentStyle,
  type CardListAccentStyle,
} from '@/app/ops-analysis/utils/cardList';
import { buildPersistedNetworkStatusTopologyConfig } from '@/app/ops-analysis/utils/networkStatusTopologyLayout';
import { validateComponentSwitchParams } from '@/app/ops-analysis/utils/componentParamSwitch';

export interface WidgetConfigFormValues {
  name: string;
  description?: string;
  chartType: string;
  sceneWidgetType?: SceneWidgetType;
  networkStatusTopology?: NetworkStatusTopologyConfig;
  chartThemeMode?: OpsChartThemeMode;
  dataSource?: string | number;
  compare?: boolean;
  compareMode?: 'percent' | 'value';
  dataSourceParams?: ParamItem[];
  params?: Record<string, string | number | boolean | [number, number] | null>;
  tableConfig?: TableConfig;
  selectedFields?: string[];
  descriptionField?: string;
  topNLabelField?: string;
  topNValueField?: string;
  unit?: string;
  unitId?: string;
  valueMappings?: ValueConfig['valueMappings'];
  conversionFactor?: number;
  decimalPlaces?: number;
  gaugeMin?: number;
  gaugeMax?: number;
  gaugeShape?: 'semicircle' | 'circle';
  eventTimeline?: ValueConfig['eventTimeline'];
  radar?: ValueConfig['radar'];
  cardList?: {
    titleField?: string;
    descriptionField?: string;
    leading?: {
      type?: 'none' | 'index' | 'field';
      field?: string;
      style?: CardListAccentStyle;
    };
    badgeField?: string;
    badgeStyle?: CardListAccentStyle;
    trailingPrimaryField?: string;
    trailingSecondaryField?: string;
    layout?: 'list' | 'grid';
  };
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
  | 'multipleComponentSwitchParams'
  | 'cardListTitleRequired'
  | 'cardListLeadingFieldRequired';

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

const buildWidgetConfigBase = (
  values: WidgetConfigFormValues,
  chartType: string,
): WidgetConfig => ({
  name: values.name,
  ...(values.description ? { description: values.description } : {}),
  chartType,
  ...(values.dataSource !== undefined ? { dataSource: values.dataSource } : {}),
  ...(values.dataSourceParams ? { dataSourceParams: values.dataSourceParams } : {}),
  ...(values.appearance ? { appearance: values.appearance } : {}),
});

const buildSceneWidgetConfig = (
  values: WidgetConfigFormValues,
): WidgetConfig => {
  if (values.sceneWidgetType === 'application3D') {
    return {
      name: values.name,
      description: values.description,
      chartType: 'application3D',
      sceneWidgetType: 'application3D',
      appearance: values.appearance || { frame: 'bare' },
    };
  }
  const topologyConfig = values.networkStatusTopology;
  return {
    name: values.name,
    description: values.description,
    chartType: 'networkStatusTopology',
    sceneWidgetType: 'networkStatusTopology',
    networkStatusTopology: buildPersistedNetworkStatusTopologyConfig({
      instUuids: topologyConfig?.instUuids || [],
      nodeLimit: topologyConfig?.nodeLimit,
      linkTrafficDisplays: topologyConfig?.linkTrafficDisplays,
      inboundTrafficThresholds: topologyConfig?.inboundTrafficThresholds,
      outboundTrafficThresholds: topologyConfig?.outboundTrafficThresholds,
      layoutMode: topologyConfig?.layoutMode,
      layoutByMode: topologyConfig?.layoutByMode,
      nodePositions: topologyConfig?.nodePositions,
      linkVertices: topologyConfig?.linkVertices,
    }),
    appearance: values.appearance,
  };
};

const buildTableConfig = ({
  displayColumns,
  filterFields,
  showTableFilterFields,
  includeCellStyle,
}: Pick<
  BuildWidgetSubmitConfigInput,
  'displayColumns' | 'filterFields' | 'showTableFilterFields'
> & { includeCellStyle: boolean }): BuildWidgetSubmitConfigResult & { tableConfig?: TableConfig } => {
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
    tableConfig.columns = validDisplayColumns.map((column, index) => {
      const next: TableColumnConfigItem = {
        key: column.key,
        title: column.title,
        visible: column.visible,
        order: index,
        columnType: column.columnType,
      };
      if (column.columnType === 'actions' || !includeCellStyle) {
        return next;
      }
      if (column.cellType === 'colorBackground') {
        next.cellType = 'colorBackground';
      }
      if (column.valueMappings?.length) {
        next.valueMappings = column.valueMappings;
      }
      if (column.cellThresholdColors?.length) {
        next.cellThresholdColors = column.cellThresholdColors;
      }
      return next;
    });
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
  result.compareMode = values.compareMode || 'percent';
  const descriptionField = values.descriptionField?.trim();
  if (descriptionField) {
    result.descriptionField = descriptionField;
  }
  applyValueFormatFields(result, values);
  result.valueMappings = values.valueMappings || undefined;
};

const trimOptionalField = (value?: string) => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
};

const CARD_LIST_FOREIGN_KEYS = [
  'tableConfig',
  'actions',
  'eventTimeline',
  'radar',
  'selectedFields',
  'descriptionField',
  'topNLabelField',
  'topNValueField',
] as const;

const OPTIONAL_NUMERIC_DISPLAY_FIELDS = [
  'conversionFactor',
  'decimalPlaces',
] as const;

const applyOptionalNumericDisplayFields = (
  result: WidgetConfig,
  values: WidgetConfigFormValues,
) => {
  for (const key of OPTIONAL_NUMERIC_DISPLAY_FIELDS) {
    if (isFiniteNumber(values[key])) {
      result[key] = values[key];
    } else if (values[key] === null) {
      // InputNumber 清空后的显式 sentinel，供 merge/spread 覆盖旧值后再剥离
      (result as unknown as Record<string, unknown>)[key] = null;
    }
  }
};

const applyValueFormatFields = (
  result: WidgetConfig,
  values: WidgetConfigFormValues,
) => {
  if (values.unit !== undefined) result.unit = values.unit;
  result.unitId = values.unitId;
  applyOptionalNumericDisplayFields(result, values);
};

const VALUE_FORMAT_CHART_TYPES = new Set(['line', 'bar', 'pie', 'multiValue']);

const stripUnsetOptionalNumericDisplayFields = <T extends object>(
  valueConfig: T,
): T => {
  const next = { ...valueConfig } as T & Record<string, unknown>;
  for (const key of OPTIONAL_NUMERIC_DISPLAY_FIELDS) {
    if (!isFiniteNumber(next[key])) {
      delete next[key];
    }
  }
  return next;
};

export const omitForeignChartTypeFields = <T extends object>(
  valueConfig: T,
  chartType: string,
): T => {
  const next = { ...valueConfig } as T & Record<string, unknown>;
  if (chartType === 'cardList') {
    for (const key of CARD_LIST_FOREIGN_KEYS) {
      delete next[key];
    }
  } else {
    delete next.cardList;
  }
  if (chartType === 'multiValue') {
    if (!Array.isArray(next.thresholdColors) || next.thresholdColors.length === 0) {
      delete next.thresholdColors;
    }
    if (!Array.isArray(next.valueMappings) || next.valueMappings.length === 0) {
      delete next.valueMappings;
    }
  }
  return stripUnsetOptionalNumericDisplayFields(next);
};

/**
 * Dashboard 编辑保存边界：先合并旧 valueConfig 与本次提交字段，
 * 再按最终 chartType 去掉其它图表专属配置。
 * 与 Screen 侧 omitForeignChartTypeFields(...) 语义一致，固定走 ValueConfig。
 */
export const mergeSanitizedWidgetValueConfig = (
  existingValueConfig: ValueConfig | undefined,
  nextFields: ValueConfig,
  chartType: string,
): ValueConfig =>
  omitForeignChartTypeFields(
    {
      ...(existingValueConfig || {}),
      ...nextFields,
    },
    chartType,
  );

const applyCardListConfig = (
  result: WidgetConfig,
  values: WidgetConfigFormValues,
): WidgetSubmitError | undefined => {
  const titleField = values.cardList?.titleField?.trim() || '';
  if (!titleField) {
    return 'cardListTitleRequired';
  }

  const leadingStyle = normalizeCardListAccentStyle(
    values.cardList?.leading?.style,
  );
  const leadingType = values.cardList?.leading?.type;
  let leading: CardListConfig['leading'];
  if (leadingType === 'field') {
    const field = values.cardList?.leading?.field?.trim() || '';
    if (!field) {
      return 'cardListLeadingFieldRequired';
    }
    leading = {
      type: 'field',
      field,
      ...(leadingStyle ? { style: leadingStyle } : {}),
    };
  } else if (leadingType === 'index') {
    leading = {
      type: 'index',
      ...(leadingStyle ? { style: leadingStyle } : {}),
    };
  }

  const cardList: CardListConfig = { titleField };
  if (leading) {
    cardList.leading = leading;
  }

  const descriptionField = trimOptionalField(values.cardList?.descriptionField);
  if (descriptionField) {
    cardList.descriptionField = descriptionField;
  }
  const badgeField = trimOptionalField(values.cardList?.badgeField);
  if (badgeField) {
    cardList.badgeField = badgeField;
    const badgeStyle = normalizeCardListAccentStyle(values.cardList?.badgeStyle);
    if (badgeStyle) {
      cardList.badgeStyle = badgeStyle;
    }
  }
  const trailingPrimaryField = trimOptionalField(
    values.cardList?.trailingPrimaryField,
  );
  if (trailingPrimaryField) {
    cardList.trailingPrimaryField = trailingPrimaryField;
  }
  const trailingSecondaryField = trimOptionalField(
    values.cardList?.trailingSecondaryField,
  );
  if (trailingSecondaryField) {
    cardList.trailingSecondaryField = trailingSecondaryField;
  }
  if (values.cardList?.layout === 'grid') {
    cardList.layout = 'grid';
  }

  result.cardList = cardList;
  return undefined;
};

const applyGaugeConfig = (
  result: WidgetConfig,
  values: WidgetConfigFormValues,
  selectedFields: string[],
  thresholdColors: ThresholdColorConfig[],
) => {
  result.selectedFields = selectedFields;
  result.thresholdColors = thresholdColors;
  applyValueFormatFields(result, values);
  result.valueMappings = values.valueMappings || undefined;
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
  if (values.sceneWidgetType) {
    return { config: buildSceneWidgetConfig(values) };
  }

  const result: WidgetConfig = buildWidgetConfigBase(values, chartType);
  if (validateComponentSwitchParams(values.dataSourceParams)) {
    return { error: 'multipleComponentSwitchParams' };
  }

  if (chartType === 'table' || chartType === 'eventTable') {
    const tableResult = buildTableConfig({
      displayColumns,
      filterFields,
      showTableFilterFields,
      includeCellStyle: chartType === 'table',
    });
    if (tableResult.error) {
      return { error: tableResult.error };
    }
    if (tableResult.tableConfig) {
      result.tableConfig = tableResult.tableConfig;
    }
  }

  if (!showChartThemeMode) {
    // chartThemeMode is omitted by default
  } else if (values.chartThemeMode && values.chartThemeMode !== 'default') {
    result.chartThemeMode = values.chartThemeMode;
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

  if (VALUE_FORMAT_CHART_TYPES.has(chartType)) {
    applyValueFormatFields(result, values);
  }

  if (chartType === 'multiValue') {
    result.thresholdColors = thresholdColors;
    result.valueMappings = values.valueMappings || [];
  }

  if (chartType === 'topN') {
    result.topNLabelField = values.topNLabelField;
    result.topNValueField = values.topNValueField;
  }

  if (chartType === 'eventTimeline') {
    result.eventTimeline = {
      sortOrder: values.eventTimeline?.sortOrder || 'desc',
    };
  }

  if (chartType === 'radar') {
    const indicators = (values.radar?.indicators || [])
      .map((item) => ({
        key: String(item.key || '').trim(),
        label: String(item.label || '').trim() || undefined,
      }))
      .filter((item) => item.key);

    result.radar = {
      min: values.radar?.min,
      max: values.radar?.max,
      indicators,
    };
  }

  if (chartType === 'cardList') {
    const cardListError = applyCardListConfig(result, values);
    if (cardListError) {
      return { error: cardListError };
    }
  }

  if (filterBindings && Object.keys(filterBindings).length > 0) {
    result.filterBindings = filterBindings;
  }

  return { config: result };
};
