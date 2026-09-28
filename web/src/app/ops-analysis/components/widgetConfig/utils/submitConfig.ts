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
  RelatedTopologyConfig,
  Room3DConfig,
  SceneWidgetType,
} from '@/app/ops-analysis/types/sceneWidget';
import {
  normalizeCardListAccentStyle,
  type CardListAccentStyle,
} from '@/app/ops-analysis/utils/cardList';
import { buildPersistedNetworkStatusTopologyConfig } from '@/app/ops-analysis/utils/networkStatusTopologyLayout';
import { validateComponentSwitchParams } from '@/app/ops-analysis/utils/componentParamSwitch';
import { persistRoom3DConfig } from '@/app/ops-analysis/utils/room3DConfig';
import {
  resolveApplication3DWallConfig,
  type Application3DWallConfig,
} from '@/app/ops-analysis/utils/application3DWallConfig';

export interface WidgetConfigFormValues {
  name: string;
  description?: string;
  chartType: string;
  sceneWidgetType?: SceneWidgetType;
  networkStatusTopology?: NetworkStatusTopologyConfig;
  relatedTopology?: RelatedTopologyConfig;
  room3D?: Room3DConfig;
  application3DWall?: Application3DWallConfig;
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
  dimensionField?: string;
  valueField?: string;
  multiValueLabelField?: string;
  multiValueValueField?: string;
  nodeGraphIdentityMode?: 'ip' | 'service';
  nodeGraphSourceField?: string;
  nodeGraphTargetField?: string;
  nodeGraphValueField?: string;
  nodeGraphTargetPortField?: string;
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
  | 'cardListLeadingFieldRequired'
  | 'chartRoleFieldsRequired'
  | 'chartRoleFieldPairRequired'
  | 'relatedTopologyInstUuidRequired'
  | 'relatedTopologyModelIdRequired';

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
  /** 预览组装：映射与提交相同，但不因未填必填项拦截。 */
  forPreview?: boolean;
}

export interface BuildWidgetSubmitConfigResult {
  config?: WidgetConfig;
  error?: WidgetSubmitError;
}

export const persistRelatedTopologyConfig = (
  config?: RelatedTopologyConfig,
): RelatedTopologyConfig => {
  const modelId = config?.modelId?.trim() || '';
  const instUuid = config?.instUuid?.trim() || '';
  return {
    ...(modelId ? { modelId } : {}),
    ...(instUuid ? { instUuid } : {}),
  };
};

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
      application3DWall: resolveApplication3DWallConfig(values.application3DWall),
      appearance: values.appearance || { frame: 'bare' },
    };
  }
  if (values.sceneWidgetType === 'relatedTopology') {
    return {
      name: values.name,
      description: values.description,
      chartType: 'relatedTopology',
      sceneWidgetType: 'relatedTopology',
      relatedTopology: persistRelatedTopologyConfig(values.relatedTopology),
      appearance: values.appearance,
    };
  }
  if (values.sceneWidgetType === 'room3D') {
    return {
      name: values.name,
      description: values.description,
      chartType: 'room3D',
      sceneWidgetType: 'room3D',
      room3D: persistRoom3DConfig(values.room3D),
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
  forPreview = false,
}: Pick<
  BuildWidgetSubmitConfigInput,
  'displayColumns' | 'filterFields' | 'showTableFilterFields' | 'forPreview'
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

  if (hasDuplicateKeys && !forPreview) {
    return { error: 'duplicateFieldKey' };
  }

  const hasVisibleColumn = validDisplayColumns.some(
    (column) => column.visible !== false,
  );
  if (!hasVisibleColumn && !forPreview) {
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
  'dimensionField',
  'valueField',
  'multiValueLabelField',
  'multiValueValueField',
  'nodeGraphIdentityMode',
  'nodeGraphSourceField',
  'nodeGraphTargetField',
  'nodeGraphValueField',
  'nodeGraphTargetPortField',
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

const VALUE_FORMAT_CHART_TYPES = new Set([
  'line',
  'bar',
  'pie',
  'multiValue',
  'nodeGraph',
]);

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
  forPreview = false,
): WidgetSubmitError | undefined => {
  const titleField = values.cardList?.titleField?.trim() || '';
  if (!titleField) {
    if (forPreview) {
      return undefined;
    }
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
      if (!forPreview) {
        return 'cardListLeadingFieldRequired';
      }
    } else {
      leading = {
        type: 'field',
        field,
        ...(leadingStyle ? { style: leadingStyle } : {}),
      };
    }
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
  forPreview = false,
}: BuildWidgetSubmitConfigInput): BuildWidgetSubmitConfigResult => {
  if (values.sceneWidgetType) {
    if (values.sceneWidgetType === 'relatedTopology' && !forPreview) {
      const modelId = values.relatedTopology?.modelId?.trim() || '';
      const instUuid = values.relatedTopology?.instUuid?.trim() || '';
      if (!modelId) {
        return { error: 'relatedTopologyModelIdRequired' };
      }
      if (!instUuid) {
        return { error: 'relatedTopologyInstUuidRequired' };
      }
    }
    return { config: buildSceneWidgetConfig(values) };
  }

  const result: WidgetConfig = buildWidgetConfigBase(values, chartType);
  if (validateComponentSwitchParams(values.dataSourceParams) && !forPreview) {
    return { error: 'multipleComponentSwitchParams' };
  }

  if (chartType === 'table' || chartType === 'eventTable') {
    const tableResult = buildTableConfig({
      displayColumns,
      filterFields,
      showTableFilterFields,
      includeCellStyle: chartType === 'table',
      forPreview,
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

  if (chartType === 'line' || chartType === 'bar' || chartType === 'pie') {
    const dimensionField = trimOptionalField(values.dimensionField);
    const valueField = trimOptionalField(values.valueField);
    if (Boolean(dimensionField) !== Boolean(valueField) && !forPreview) {
      return { error: 'chartRoleFieldPairRequired' };
    }
    if (dimensionField) {
      result.dimensionField = dimensionField;
    }
    if (valueField) {
      result.valueField = valueField;
    }
  }

  if (chartType === 'multiValue') {
    result.thresholdColors = thresholdColors;
    result.valueMappings = values.valueMappings || [];
    const labelField = trimOptionalField(values.multiValueLabelField);
    const valueField = trimOptionalField(values.multiValueValueField);
    if ((!labelField || !valueField) && !forPreview) {
      return { error: 'chartRoleFieldsRequired' };
    }
    if (labelField) {
      result.multiValueLabelField = labelField;
    }
    if (valueField) {
      result.multiValueValueField = valueField;
    }
  }

  if (chartType === 'topN') {
    result.topNLabelField = values.topNLabelField;
    result.topNValueField = values.topNValueField;
  }

  if (chartType === 'nodeGraph') {
    const identityMode = values.nodeGraphIdentityMode || 'ip';
    result.nodeGraphIdentityMode = identityMode;
    result.nodeGraphSourceField = values.nodeGraphSourceField;
    result.nodeGraphTargetField = values.nodeGraphTargetField;
    result.nodeGraphValueField = values.nodeGraphValueField;
    if (identityMode === 'service') {
      result.nodeGraphTargetPortField = values.nodeGraphTargetPortField;
    }
  }

  if (chartType === 'eventTimeline') {
    const timeField = trimOptionalField(values.eventTimeline?.timeField);
    const titleField = trimOptionalField(values.eventTimeline?.titleField);
    if ((!timeField || !titleField) && !forPreview) {
      return { error: 'chartRoleFieldsRequired' };
    }
    const descriptionField = trimOptionalField(values.eventTimeline?.descriptionField);
    const categoryField = trimOptionalField(values.eventTimeline?.categoryField);
    const statusField = trimOptionalField(values.eventTimeline?.statusField);
    const linkField = trimOptionalField(values.eventTimeline?.linkField);
    result.eventTimeline = {
      sortOrder: values.eventTimeline?.sortOrder || 'desc',
      ...(timeField ? { timeField } : {}),
      ...(titleField ? { titleField } : {}),
      ...(descriptionField ? { descriptionField } : {}),
      ...(categoryField ? { categoryField } : {}),
      ...(statusField ? { statusField } : {}),
      ...(linkField ? { linkField } : {}),
    };
  }

  if (chartType === 'radar') {
    const indicators = (values.radar?.indicators || [])
      .map((item) => ({
        key: String(item.key || '').trim(),
        label: String(item.label || '').trim() || undefined,
      }))
      .filter((item) => item.key);
    const arrayNameField = trimOptionalField(values.radar?.arrayNameField);
    const arrayValueField = trimOptionalField(values.radar?.arrayValueField);
    if (indicators.length === 0 && (!arrayNameField || !arrayValueField) && !forPreview) {
      return { error: 'chartRoleFieldsRequired' };
    }

    result.radar = {
      min: values.radar?.min,
      max: values.radar?.max,
      indicators,
      ...(arrayNameField ? { arrayNameField } : {}),
      ...(arrayValueField ? { arrayValueField } : {}),
    };
  }

  if (chartType === 'cardList') {
    const cardListError = applyCardListConfig(result, values, forPreview);
    if (cardListError) {
      return { error: cardListError };
    }
  }

  if (filterBindings && Object.keys(filterBindings).length > 0) {
    result.filterBindings = filterBindings;
  }

  return { config: result };
};

/** 预览用：与提交同一套字段映射，不因未填名称/列等拦截。 */
export const buildWidgetDraftConfig = (
  input: BuildWidgetSubmitConfigInput,
): WidgetConfig | undefined =>
  buildWidgetSubmitConfig({ ...input, forPreview: true }).config;
