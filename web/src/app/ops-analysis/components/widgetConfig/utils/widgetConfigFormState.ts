import type {
  FilterValue,
  UnifiedFilterDefinition,
  ValueConfig,
  ViewConfigItem,
  WidgetConfig,
} from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  NetworkStatusTopologyConfig,
  SceneWidgetType,
} from '@/app/ops-analysis/types/sceneWidget';
import { isSceneWidgetType } from '@/app/ops-analysis/types/sceneWidgetCapability';
import { resolveApplication3DWallConfig } from '@/app/ops-analysis/utils/application3DWallConfig';
import {
  hydrateRoom3DConfig,
  readPersistedServerRoomId,
} from '@/app/ops-analysis/utils/room3DConfig';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';
import { canEnableCompare } from '@/app/ops-analysis/utils/compareQuery';
import {
  getDefaultScreenWidgetAppearance,
  resolveScreenWidgetAppearance,
} from '@/app/ops-analysis/(pages)/view/screen/utils/layoutUtils';
import {
  getBindableFilterParams,
  getFilterDefinitionId,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import type { WidgetConfigFormValues } from './submitConfig';

export const NETWORK_STATUS_TOPOLOGY = 'networkStatusTopology';
export const VALUE_FORMAT_CHART_TYPES = new Set([
  'line',
  'bar',
  'pie',
  'multiValue',
  'nodeGraph',
]);

export interface SelectorLike {
  id?: unknown;
  chartType?: unknown;
  sceneWidgetType?: unknown;
}

export interface WidgetChartTypeFlags {
  isTableLike: boolean;
  isNetworkStatusTopology: boolean;
  isRelatedTopology: boolean;
  isRoom3D: boolean;
  isApplication3D: boolean;
  isSceneWidget: boolean;
  showValueFormat: boolean;
}

export function getSceneWidgetSelectionType(
  item?: SelectorLike | null,
): SceneWidgetType | undefined {
  if (!item) return undefined;
  for (const value of [item.sceneWidgetType, item.chartType]) {
    if (typeof value === 'string' && isSceneWidgetType(value)) return value;
  }
  if (typeof item.id === 'string' && item.id.startsWith('scene:')) {
    const value = item.id.slice('scene:'.length);
    if (isSceneWidgetType(value)) return value;
  }
  return undefined;
}

export const isSceneWidgetSelection = (item?: SelectorLike | null): boolean => {
  return Boolean(getSceneWidgetSelectionType(item));
};

export function getWidgetChartTypeFlags(
  chartType: string,
  sceneWidgetType?: unknown,
): WidgetChartTypeFlags {
  const sceneType =
    typeof sceneWidgetType === 'string' ? sceneWidgetType : undefined;
  return {
    isTableLike: chartType === 'table' || chartType === 'eventTable',
    isNetworkStatusTopology:
      chartType === 'networkStatusTopology' ||
      sceneType === 'networkStatusTopology',
    isRelatedTopology:
      chartType === 'relatedTopology' || sceneType === 'relatedTopology',
    isRoom3D: chartType === 'room3D' || sceneType === 'room3D',
    isApplication3D: chartType === 'application3D' || sceneType === 'application3D',
    isSceneWidget:
      isSceneWidgetType(chartType) || isSceneWidgetType(sceneType),
    showValueFormat: VALUE_FORMAT_CHART_TYPES.has(chartType),
  };
}

export const buildDataFetchSignature = (
  config: WidgetConfig | undefined,
): string => {
  if (!config) return '';
  return JSON.stringify({
    dataSource: config.dataSource,
    chartType: config.chartType,
    sceneWidgetType: config.sceneWidgetType,
    compare: Boolean(config.compare),
    compareMode: config.compareMode,
    filterBindings: config.filterBindings,
    dataSourceParams: Array.isArray(config.dataSourceParams)
      ? config.dataSourceParams.map((p) => ({ name: p.name, value: p.value }))
      : [],
    topNLabelField: config.topNLabelField,
    topNValueField: config.topNValueField,
    cardListTitleField: config.cardList?.titleField,
    networkStatusTopology: config.networkStatusTopology
      ? {
        instUuids: config.networkStatusTopology.instUuids,
        nodeLimit: config.networkStatusTopology.nodeLimit,
        linkTrafficDisplays: config.networkStatusTopology.linkTrafficDisplays,
      }
      : undefined,
    room3D: config.room3D?.serverRoomId || undefined,
  });
};

export const computePreviewDefinitions = (
  existingDefinitions: UnifiedFilterDefinition[],
  dataSource: DatasourceItem | undefined,
): UnifiedFilterDefinition[] => {
  const existingMap = new Map(
    existingDefinitions.map((def) => [def.id, def]),
  );
  const bindableParams = getBindableFilterParams(dataSource?.params);
  bindableParams.forEach((param, index) => {
    const id = getFilterDefinitionId(param.name, param.type);
    if (!existingMap.has(id)) {
      existingMap.set(id, {
        id,
        key: param.name,
        name: param.alias_name || param.name,
        type: param.type,
        defaultValue: (param.value as FilterValue) ?? null,
        order: existingDefinitions.length + index,
        enabled: true,
      });
    }
  });
  return Array.from(existingMap.values());
};

export function resolveOpenedSceneWidgetType(
  valueConfig?: ValueConfig,
): SceneWidgetType | undefined {
  if (isSceneWidgetType(valueConfig?.sceneWidgetType)) {
    return valueConfig.sceneWidgetType;
  }
  if (isSceneWidgetType(valueConfig?.chartType)) {
    return valueConfig.chartType;
  }
  return undefined;
}

export function buildOpenedSceneWidgetTopology(
  valueConfig?: ValueConfig,
): NetworkStatusTopologyConfig {
  const networkStatusTopology = valueConfig?.networkStatusTopology || {
    instUuids: [],
    nodeLimit: 100,
  };
  return {
    ...networkStatusTopology,
    linkTrafficDisplays: Array.isArray(networkStatusTopology.linkTrafficDisplays)
      ? networkStatusTopology.linkTrafficDisplays
      : ['inbound', 'outbound'],
  };
}

function buildClearedChartDependentFormFields() {
  return {
    selectedFields: [] as string[],
    topNLabelField: undefined,
    topNValueField: undefined,
    dimensionField: undefined,
    valueField: undefined,
    multiValueLabelField: undefined,
    multiValueValueField: undefined,
    nodeGraphIdentityMode: 'ip' as const,
    nodeGraphSourceField: undefined,
    nodeGraphTargetField: undefined,
    nodeGraphValueField: undefined,
    nodeGraphTargetPortField: undefined,
    unit: undefined,
    unitId: undefined,
    valueMappings: undefined,
    conversionFactor: undefined,
    decimalPlaces: undefined,
    gaugeMin: 0,
    gaugeMax: 100,
    gaugeShape: 'semicircle' as const,
    eventTimeline: {
      sortOrder: 'desc' as const,
    },
    radar: {
      min: 0,
      max: 100,
      indicators: [],
    },
    cardList: {
      leading: { type: 'none' as const },
      layout: 'list' as const,
    },
    compare: false,
    compareMode: 'percent' as const,
  };
}

/** 选择器切到场景组件时写入 Form 的字段。不含 name，避免冲掉已填标题。 */
export function buildSceneWidgetSelectorResetValues(
  sceneWidgetType: string,
  surface?: OpsAnalysisWidgetSurface,
) {
  return {
    ...buildClearedChartDependentFormFields(),
    chartType: sceneWidgetType,
    sceneWidgetType: sceneWidgetType as SceneWidgetType,
    appearance:
      surface === 'screen'
        ? getDefaultScreenWidgetAppearance(sceneWidgetType)
        : undefined,
    dataSource: undefined,
    networkStatusTopology: {
      instUuids: [] as string[],
      nodeLimit: 100,
      linkTrafficDisplays: ['inbound', 'outbound'] as Array<
        'inbound' | 'outbound'
      >,
    },
    relatedTopology: {
      instUuid: undefined,
      modelId: undefined,
    },
    room3D: hydrateRoom3DConfig({}),
    application3DWall: resolveApplication3DWallConfig(undefined),
    params: {},
    dataSourceParams: [] as WidgetConfigFormValues['dataSourceParams'],
    tableConfig: undefined,
    actions: [] as WidgetConfigFormValues['actions'],
  };
}

/** 选择器切到普通数据源时写入 Form 的字段。与场景重置分开，不带 tableConfig/actions。 */
export function buildDatasourceSwitchResetValues(options: {
  dataSourceId: string | number;
  chartType: string;
  params: Record<string, any>;
  surface?: OpsAnalysisWidgetSurface;
}) {
  return {
    ...buildClearedChartDependentFormFields(),
    dataSource: options.dataSourceId,
    chartType: options.chartType,
    appearance:
      options.surface === 'screen'
        ? getDefaultScreenWidgetAppearance(options.chartType)
        : undefined,
    sceneWidgetType: undefined,
    networkStatusTopology: undefined,
    relatedTopology: undefined,
    room3D: undefined,
    application3DWall: undefined,
    params: options.params,
  };
}

export function buildOpenedWidgetFormValues(
  widgetItem: ViewConfigItem,
  options: {
    showChartThemeMode: boolean;
    surface?: OpsAnalysisWidgetSurface;
  },
): WidgetConfigFormValues {
  const valueConfig = widgetItem.valueConfig;
  return {
    name: widgetItem?.name || '',
    description: widgetItem.description || '',
    chartType: valueConfig?.chartType || '',
    sceneWidgetType: valueConfig?.sceneWidgetType,
    networkStatusTopology: valueConfig?.networkStatusTopology,
    relatedTopology: valueConfig?.relatedTopology,
    room3D: hydrateRoom3DConfig({
      ...valueConfig?.room3D,
      serverRoomId: readPersistedServerRoomId(valueConfig),
    }),
    application3DWall: resolveApplication3DWallConfig(valueConfig?.application3DWall),
    chartThemeMode: options.showChartThemeMode
      ? valueConfig?.chartThemeMode || 'default'
      : undefined,
    appearance:
      options.surface === 'screen'
        ? resolveScreenWidgetAppearance(
          valueConfig?.chartType,
          valueConfig?.appearance,
        )
        : undefined,
    dataSource: valueConfig?.dataSource || '',
    dataSourceParams: valueConfig?.dataSourceParams || [],
    params: {},
    tableConfig: valueConfig?.tableConfig,
    actions: valueConfig?.actions || [],
  };
}

export function applyOpenedValueConfigToFormValues(
  formValues: WidgetConfigFormValues,
  valueConfig: ValueConfig | undefined,
  targetDataSource: DatasourceItem | undefined,
): WidgetConfigFormValues {
  if (valueConfig?.selectedFields) {
    formValues.selectedFields = valueConfig.selectedFields;
  } else {
    formValues.selectedFields = [];
  }

  if (valueConfig?.descriptionField !== undefined) {
    formValues.descriptionField = valueConfig.descriptionField;
  } else {
    formValues.descriptionField = undefined;
  }

  if (valueConfig?.topNLabelField !== undefined) {
    formValues.topNLabelField = valueConfig.topNLabelField;
  }
  if (valueConfig?.topNValueField !== undefined) {
    formValues.topNValueField = valueConfig.topNValueField;
  }
  if (valueConfig?.dimensionField !== undefined) {
    formValues.dimensionField = valueConfig.dimensionField;
  }
  if (valueConfig?.valueField !== undefined) {
    formValues.valueField = valueConfig.valueField;
  }
  if (valueConfig?.multiValueLabelField !== undefined) {
    formValues.multiValueLabelField = valueConfig.multiValueLabelField;
  }
  if (valueConfig?.multiValueValueField !== undefined) {
    formValues.multiValueValueField = valueConfig.multiValueValueField;
  }
  if (valueConfig?.nodeGraphIdentityMode !== undefined) {
    formValues.nodeGraphIdentityMode = valueConfig.nodeGraphIdentityMode;
  } else if (valueConfig?.chartType === 'nodeGraph') {
    formValues.nodeGraphIdentityMode = 'ip';
  }
  if (valueConfig?.nodeGraphSourceField !== undefined) {
    formValues.nodeGraphSourceField = valueConfig.nodeGraphSourceField;
  }
  if (valueConfig?.nodeGraphTargetField !== undefined) {
    formValues.nodeGraphTargetField = valueConfig.nodeGraphTargetField;
  }
  if (valueConfig?.nodeGraphValueField !== undefined) {
    formValues.nodeGraphValueField = valueConfig.nodeGraphValueField;
  }
  if (valueConfig?.nodeGraphTargetPortField !== undefined) {
    formValues.nodeGraphTargetPortField = valueConfig.nodeGraphTargetPortField;
  }
  if (valueConfig?.unit !== undefined) {
    formValues.unit = valueConfig.unit;
  }
  if (valueConfig?.unitId !== undefined) {
    formValues.unitId = valueConfig.unitId;
  }
  if (valueConfig?.valueMappings !== undefined) {
    formValues.valueMappings = valueConfig.valueMappings;
  }
  if (valueConfig?.conversionFactor !== undefined) {
    formValues.conversionFactor = valueConfig.conversionFactor;
  }
  if (valueConfig?.decimalPlaces !== undefined) {
    formValues.decimalPlaces = valueConfig.decimalPlaces;
  }
  if (valueConfig?.gaugeMin !== undefined) {
    formValues.gaugeMin = valueConfig.gaugeMin;
  }
  if (valueConfig?.gaugeMax !== undefined) {
    formValues.gaugeMax = valueConfig.gaugeMax;
  }
  if (valueConfig?.gaugeShape !== undefined) {
    formValues.gaugeShape = valueConfig.gaugeShape;
  }
  if (valueConfig?.eventTimeline !== undefined) {
    formValues.eventTimeline = valueConfig.eventTimeline;
  }
  if (valueConfig?.radar !== undefined) {
    formValues.radar = valueConfig.radar;
  }
  if (valueConfig?.cardList !== undefined) {
    formValues.cardList = {
      ...valueConfig.cardList,
      leading: valueConfig.cardList.leading || { type: 'none' },
      layout: valueConfig.cardList.layout || 'list',
    };
  } else {
    formValues.cardList = {
      leading: { type: 'none' },
      layout: 'list',
    };
  }
  if (valueConfig?.compare !== undefined) {
    formValues.compare = valueConfig.compare && canEnableCompare({
      config: { chartType: 'single', dataSourceParams: targetDataSource?.params },
      dataSource: targetDataSource,
    });
  }
  formValues.compareMode = valueConfig?.compareMode || 'percent';
  return formValues;
}

export function mergeNetworkStatusTopologyDraft(
  formTopology: NetworkStatusTopologyConfig | undefined,
  existingTopology: NetworkStatusTopologyConfig | undefined,
): NetworkStatusTopologyConfig {
  return {
    instUuids: formTopology?.instUuids || existingTopology?.instUuids || [],
    nodeLimit: formTopology?.nodeLimit ?? existingTopology?.nodeLimit ?? 100,
    linkTrafficDisplays:
      formTopology?.linkTrafficDisplays ?? existingTopology?.linkTrafficDisplays,
    inboundTrafficThresholds:
      formTopology?.inboundTrafficThresholds ??
      existingTopology?.inboundTrafficThresholds,
    outboundTrafficThresholds:
      formTopology?.outboundTrafficThresholds ??
      existingTopology?.outboundTrafficThresholds,
    layoutMode: formTopology?.layoutMode ?? existingTopology?.layoutMode,
    layoutByMode:
      formTopology?.layoutByMode ?? existingTopology?.layoutByMode,
    nodePositions:
      formTopology?.nodePositions ?? existingTopology?.nodePositions,
    linkVertices:
      formTopology?.linkVertices ?? existingTopology?.linkVertices,
  };
}
