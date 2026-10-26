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
import { normalizeInteractionLink } from '@/app/ops-analysis/utils/interactionLink';
import {
  isFiniteNumber,
  type ThresholdColorConfig,
} from '@/app/ops-analysis/utils/thresholdUtils';
import {
  type ApplicationTopologyConfig,
  type NetworkStatusTopologyConfig,
  type RelatedTopologyConfig,
  type Room3DConfig,
  type SceneWidgetType,
} from '@/app/ops-analysis/types/sceneWidget';
import {
  normalizeCardListAccentStyle,
  type CardListAccentStyle,
} from '@/app/ops-analysis/utils/cardList';
import { buildPersistedNetworkStatusTopologyConfig } from '@/app/ops-analysis/utils/networkStatusTopologyLayout';
import { validateComponentSwitchParams } from '@/app/ops-analysis/utils/componentParamSwitch';
import { persistRoom3DConfig } from '@/app/ops-analysis/utils/room3DConfig';
import {
  APPLICATION_TOPOLOGY_DEPTH_FILTER_ID,
  APPLICATION_TOPOLOGY_FILTER_ID,
} from '@/app/ops-analysis/utils/applicationTopologyCanvasFilter';
import { ROOM3D_FILTER_ID } from '@/app/ops-analysis/utils/room3DScreenFilter';
import { resolveOpsTableColumnWidth } from '@/app/ops-analysis/utils/opsTableColumn';
import {
  resolveApplication3DWallConfig,
  type Application3DWallConfig,
} from '@/app/ops-analysis/utils/application3DWallConfig';
import {
  persistSingleValueStyle,
  type SingleValueStyleConfig,
} from '@/app/ops-analysis/utils/singleValueStyle';

export interface WidgetConfigFormValues {
  name: string;
  description?: string;
  chartType: string;
  sceneWidgetType?: SceneWidgetType;
  networkStatusTopology?: NetworkStatusTopologyConfig;
  relatedTopology?: RelatedTopologyConfig;
  applicationTopology?: ApplicationTopologyConfig;
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
  topNScalarFields?: Array<{ field?: string; label?: string }>;
  barMode?: 'relative' | 'absolute';
  barMax?: number;
  dimensionField?: string;
  valueField?: string;
  pieScalarFields?: Array<{ field?: string; label?: string }>;
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
  singleStyle?: SingleValueStyleConfig;
  interaction?: {
    kind: 'none' | 'title' | 'data';
    name: string;
    url: string;
    openMode: 'sameTab' | 'newTab';
  };
  appearance?: ValueConfig['appearance'];
}

type SubmitDisplayColumn = TableColumnConfigItem & {
  id: string;
  isDefault?: boolean;
};

type DataSubmitColumn = Omit<SubmitDisplayColumn, 'columnType'> & {
  columnType?: 'data';
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
  | 'relatedTopologyModelIdRequired'
  | 'applicationTopologyInstUuidRequired'
  | 'applicationTopologyModelIdRequired'
  | 'applicationTopologyModelUnsupported';

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
  /** 旧操作列。提交忽略它，保存时由 applyInteractionLink 删掉 valueConfig.actions。 */
  actions?: DashboardActionConfig[];
  /** 预览组装：映射与提交相同，但不因未填必填项拦截。 */
  forPreview?: boolean;
  /**
   * 大屏样式在检查器里直接改画布，数据表单提交不能带上 singleStyle，
   * 否则会把已保存的样式覆盖或清掉。
   */
  includeSingleStyle?: boolean;
}

export interface BuildWidgetSubmitConfigResult {
  config?: WidgetConfig;
  error?: WidgetSubmitError;
}

export const persistApplicationTopologyConfig = (
  config?: ApplicationTopologyConfig,
): ApplicationTopologyConfig => {
  const depth = Number(config?.depth);
  const persistedDepth = Number.isInteger(depth) && depth >= 1 && depth <= 5 ? depth : 3;
  return {
    modelId: 'system',
    depth: persistedDepth,
  };
};

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

const applyInteractionLink = (
  result: WidgetConfig,
  values: WidgetConfigFormValues,
  chartType: string,
) => {
  const link = normalizeInteractionLink(values.interaction, chartType);
  if (link) {
    result.interaction = link;
  } else {
    delete result.interaction;
  }
  delete result.actions;
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
  if (values.sceneWidgetType === 'applicationTopology') {
    return {
      name: values.name,
      description: values.description,
      chartType: 'applicationTopology',
      sceneWidgetType: 'applicationTopology',
      applicationTopology: persistApplicationTopologyConfig(values.applicationTopology),
      filterBindings: {
        [APPLICATION_TOPOLOGY_FILTER_ID]: true,
        [APPLICATION_TOPOLOGY_DEPTH_FILTER_ID]: true,
      },
      appearance: values.appearance,
    };
  }
  if (values.sceneWidgetType === 'room3D') {
    return {
      name: values.name,
      description: values.description,
      chartType: 'room3D',
      sceneWidgetType: 'room3D',
      room3D: persistRoom3DConfig({
        rackTopLine1: values.room3D?.rackTopLine1,
        rackTopLine2: values.room3D?.rackTopLine2,
      }),
      filterBindings: { [ROOM3D_FILTER_ID]: true },
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
    .filter((column): column is DataSubmitColumn => (
      Boolean(column.key) && column.columnType !== 'actions'
    ));

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
      const columnWidth = resolveOpsTableColumnWidth(column.width);
      if (columnWidth !== undefined) {
        next.width = columnWidth;
      }
      if (!includeCellStyle) {
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
  includeSingleStyle: boolean,
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
  if (!includeSingleStyle) return;
  // 显式写入，包含 undefined，仪表盘合并时才能清掉已关闭的样式。
  result.singleStyle = persistSingleValueStyle(values.singleStyle);
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
  'topNScalarFields',
  'barMode',
  'barMax',
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
  'topN',
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
  delete next.actions;
  if (chartType !== 'single') {
    delete next.singleStyle;
  } else if (
    !next.singleStyle
    || typeof next.singleStyle !== 'object'
    || Array.isArray(next.singleStyle)
    || Object.keys(next.singleStyle).length === 0
  ) {
    delete next.singleStyle;
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
 * Dashboard 编辑保存边界：调用方会把本次表单字段逐项写入 nextFields，
 * 清空的项以 undefined 覆盖旧值。再按最终 chartType 去掉其它图表专属配置。
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

/**
 * 提交结果故意不带这些键，表示用户清空了。大屏用对象展开合并时，
 * 缺键不会覆盖旧值，所以要在这里删掉。
 */
const SCREEN_OPTIONAL_KEYS_CLEARED_WHEN_ABSENT = [
  'descriptionField',
  'dimensionField',
  'valueField',
  'nodeGraphTargetPortField',
] as const;

const isBlankOptionalValue = (value: unknown) =>
  value == null || (typeof value === 'string' && value.trim() === '');

/** 大屏组件数据配置保存：新提交覆盖旧 valueConfig，并丢掉已清空的可选项。 */
export const mergeScreenWidgetValueConfig = (
  existingValueConfig: ValueConfig | undefined,
  submitted: WidgetConfig,
  chartType: string,
): ValueConfig => {
  const merged = {
    ...(existingValueConfig || {}),
    ...submitted,
    interaction: submitted.interaction,
    actions: submitted.actions,
    chartType,
  } as ValueConfig & Record<string, unknown>;

  for (const key of SCREEN_OPTIONAL_KEYS_CLEARED_WHEN_ABSENT) {
    if (
      !Object.prototype.hasOwnProperty.call(submitted, key)
      || isBlankOptionalValue(merged[key])
    ) {
      delete merged[key];
    }
  }

  return omitForeignChartTypeFields(merged, chartType);
};

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
  result.compare = !!values.compare;
  result.compareMode = values.compareMode || 'percent';
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
  forPreview = false,
  includeSingleStyle = true,
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
    const config = buildSceneWidgetConfig(values);
    applyInteractionLink(config, values, values.sceneWidgetType);
    return { config };
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

  applyInteractionLink(result, values, chartType);

  if (chartType === 'single') {
    applySingleValueConfig(
      result,
      values,
      selectedFields,
      thresholdColors,
      includeSingleStyle,
    );
  }

  if (chartType === 'gauge') {
    applyGaugeConfig(result, values, selectedFields, thresholdColors);
  }

  if (VALUE_FORMAT_CHART_TYPES.has(chartType)) {
    applyValueFormatFields(result, values);
  }

  if (chartType === 'pie') {
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
    const scalarFields: Array<{ field: string; label?: string }> = [];
    (values.pieScalarFields || []).forEach((item) => {
      const field = trimOptionalField(item?.field);
      if (!field) {
        return;
      }
      const label = trimOptionalField(item?.label);
      scalarFields.push(label ? { field, label } : { field });
    });
    if (scalarFields.length === 1 && !forPreview) {
      return { error: 'chartRoleFieldPairRequired' };
    }
    if (scalarFields.length >= 2) {
      result.pieScalarFields = scalarFields;
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
    const scalarFields: Array<{ field: string; label?: string }> = [];
    (values.topNScalarFields || []).forEach((item) => {
      const field = trimOptionalField(item?.field);
      if (!field) {
        return;
      }
      const label = trimOptionalField(item?.label);
      scalarFields.push(label ? { field, label } : { field });
    });
    if (scalarFields.length > 0) {
      result.topNScalarFields = scalarFields;
      result.topNLabelField = undefined;
      result.topNValueField = undefined;
    } else {
      result.topNLabelField = values.topNLabelField;
      result.topNValueField = values.topNValueField;
      result.topNScalarFields = undefined;
    }
    if (values.barMode === 'absolute') {
      result.barMode = 'absolute';
      result.barMax = isFiniteNumber(values.barMax) && values.barMax > 0
        ? values.barMax
        : undefined;
    } else {
      result.barMode = undefined;
      result.barMax = undefined;
    }
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
