import type { Graph, Node } from '@antv/x6';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import type { LayoutItem, UnifiedFilterDefinition, FilterValue } from '@/app/ops-analysis/types/dashBoard';
import type { ViewConfigFormValues } from '@/app/ops-analysis/types/topology';
import {
  discoverFollowedFilterParams,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import { validateDateRangeValue } from '@/app/ops-analysis/utils/dateRange';
import {
  buildRelativeTimeRangeFilterValue,
} from '@/app/ops-analysis/utils/filterValue';
import {
  syncFilterValuesWithDefinitions,
} from '@/app/ops-analysis/utils/unifiedFilterState';
import { isFiniteNumber } from '@/app/ops-analysis/utils/thresholdUtils';

export { syncFilterValuesWithDefinitions };

export interface NamespaceOption {
  label: string;
  value: number;
}

/**
 * 从 X6 图表节点中收集命名空间选项
 * 仅从 chart 和 single-value 类型节点提取
 */
export const collectNamespaceOptionsFromNodes = (
  graphInstance: Graph | null,
  dataSources: DatasourceItem[],
  namespaceList: Array<{ id: number; name: string }>,
): NamespaceOption[] => {
  const namespaceIds = collectNamespaceIdsFromNodes(graphInstance, dataSources);

  if (namespaceIds.size === 0) return [];

  return namespaceList
    .filter((ns) => namespaceIds.has(ns.id))
    .map((ns) => ({
      label: ns.name || String(ns.id),
      value: ns.id,
    }));
};

export const collectNamespaceIdsFromNodes = (
  graphInstance: Graph | null,
  dataSources: DatasourceItem[],
): Set<number> => {
  if (!graphInstance) return new Set<number>();

  const namespaceIds = new Set<number>();
  const nodes = graphInstance.getNodes();

  nodes.forEach((node: Node) => {
    const nodeData = node.getData();
    const nodeType = nodeData?.type;

    if (nodeType !== 'chart' && nodeType !== 'single-value') {
      return;
    }

    const dsId = nodeData?.valueConfig?.dataSource;
    const normalizedId = typeof dsId === 'string' ? parseInt(dsId, 10) : dsId;
    const ds = dataSources.find((d) => d.id === normalizedId);

    if (ds?.namespaces) {
      ds.namespaces.forEach((id) => namespaceIds.add(id));
    }
  });

  return namespaceIds;
};

/**
 * 将 X6 图表节点转换为 LayoutItem 格式
 * 用于 UnifiedFilterConfigModal 组件
 */
export const convertNodesToLayoutItems = (
  graphInstance: Graph | null,
): LayoutItem[] => {
  if (!graphInstance) return [];

  const nodes = graphInstance.getNodes();
  return nodes
    .filter((node: Node) => {
      const nodeData = node.getData();
      const nodeType = nodeData?.type;
      return nodeType === 'chart' || nodeType === 'single-value' || nodeType === 'table';
    })
    .map((node: Node) => {
      const nodeData = node.getData();
      const position = node.getPosition();
      const size = node.getSize();

      return {
        i: node.id,
        x: position.x,
        y: position.y,
        w: size.width,
        h: size.height,
        name: nodeData?.name || '',
        description: nodeData?.description || '',
        valueConfig: nodeData?.valueConfig,
      };
    });
};

/**
 * 从 X6 图表节点构建筛选定义
 * 类似仪表盘的 buildFiltersFromLayout
 */
export const buildFiltersFromNodes = (
  graphInstance: Graph | null,
  dataSources: DatasourceItem[],
  previousDefinitions: UnifiedFilterDefinition[],
): UnifiedFilterDefinition[] => {
  if (!graphInstance) return previousDefinitions;

  const nodes = graphInstance.getNodes();
  const discoveredParams = discoverFollowedFilterParams(
    nodes.flatMap((node: Node) => {
      const nodeData = node.getData();
      const nodeType = nodeData?.type;

      if (nodeType !== 'chart' && nodeType !== 'single-value' && nodeType !== 'table') {
        return [];
      }

      const dataSourceId = nodeData?.valueConfig?.dataSource;
      const normalizedId = typeof dataSourceId === 'string' ? parseInt(dataSourceId, 10) : dataSourceId;
      const dataSource = dataSources.find((source) => source.id === normalizedId);
      const params = nodeData?.valueConfig?.dataSourceParams?.length
        ? nodeData.valueConfig.dataSourceParams
        : dataSource?.params;

      return [{
        params,
        filterBindings: nodeData?.valueConfig?.filterBindings,
      }];
    }),
  );

  const existingDefinitions = new Map(
    previousDefinitions.map((definition) => [definition.id, definition]),
  );

  return Array.from(discoveredParams.entries()).map(([id, param], index) => {
    const existing =
      existingDefinitions.get(id) ||
      previousDefinitions.find(
        (definition) =>
          definition.key === param.name && definition.type === param.type,
      );

    let defaultValue: FilterValue = null;
    if (existing?.defaultValue !== undefined) {
      defaultValue = existing.defaultValue;
    } else if (param.value !== undefined && param.value !== null) {
      if (param.type === 'timeRange' && typeof param.value === 'number') {
        defaultValue = buildRelativeTimeRangeFilterValue(param.value);
      } else {
        defaultValue = param.value as FilterValue;
      }
    }

    if (param.type === 'dateRange') {
      defaultValue = validateDateRangeValue(defaultValue).valid
        && defaultValue !== null
        ? { ...(defaultValue as DateRangeValue) }
        : null;
    }

    return {
      id,
      key: param.name,
      name: existing?.name || param.alias_name || param.name,
      type: param.type,
      defaultValue,
      order: existing?.order ?? index,
      enabled: existing?.enabled ?? true,
      inputMode: existing?.inputMode,
      options: existing?.options,
    };
  });
};

const VALUE_FORMAT_CHART_TYPES = new Set([
  'single',
  'gauge',
  'line',
  'bar',
  'pie',
  'multiValue',
  'nodeGraph',
  'topN',
]);

const applyValueFormatFields = (
  valueConfig: Record<string, unknown>,
  values: ViewConfigFormValues,
) => {
  if (values.unit !== undefined) valueConfig.unit = values.unit;
  if (values.unitId !== undefined) valueConfig.unitId = values.unitId;
  if (isFiniteNumber(values.conversionFactor)) {
    valueConfig.conversionFactor = values.conversionFactor;
  }
  if (isFiniteNumber(values.decimalPlaces)) {
    valueConfig.decimalPlaces = values.decimalPlaces;
  }
};

const trimOptionalField = (value?: string) => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
};

type TopNSaveValues = Pick<
  ViewConfigFormValues,
  'topNLabelField' | 'topNValueField' | 'topNScalarFields' | 'barMode' | 'barMax'
>;

/**
 * 与仪表盘 submitConfig 对齐：有标量行时去掉排名字段；相对模式不保留 barMode/barMax。
 * 在已有 valueConfig 上删除旧键，避免 `??` 把上一份绝对条宽写回去。
 */
export const applyTopNValueConfig = (
  valueConfig: Record<string, unknown>,
  values: TopNSaveValues,
): Record<string, unknown> => {
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
    valueConfig.topNScalarFields = scalarFields;
    delete valueConfig.topNLabelField;
    delete valueConfig.topNValueField;
  } else {
    delete valueConfig.topNScalarFields;
    if (values.topNLabelField !== undefined) {
      valueConfig.topNLabelField = values.topNLabelField;
    } else {
      delete valueConfig.topNLabelField;
    }
    if (values.topNValueField !== undefined) {
      valueConfig.topNValueField = values.topNValueField;
    } else {
      delete valueConfig.topNValueField;
    }
  }
  if (values.barMode === 'absolute') {
    valueConfig.barMode = 'absolute';
    if (isFiniteNumber(values.barMax) && values.barMax > 0) {
      valueConfig.barMax = values.barMax;
    } else {
      delete valueConfig.barMax;
    }
  } else {
    delete valueConfig.barMode;
    delete valueConfig.barMax;
  }
  return valueConfig;
};

/**
 * 从 ViewConfigFormValues 构建 valueConfig 对象，供图表/单值/表格节点使用。
 * @param coerceDataSource 是否将 string 类型的 dataSource 转为 number（新增节点场景）
 */
export const buildValueConfig = (
  values: ViewConfigFormValues,
  coerceDataSource = false,
): Record<string, unknown> => {
  const valueConfig: Record<string, unknown> = {
    chartType: values.chartType,
    dataSource: coerceDataSource && typeof values.dataSource === 'string'
      ? parseInt(values.dataSource, 10)
      : values.dataSource,
    dataSourceParams: values.dataSourceParams,
  };
  if (values.filterBindings && Object.keys(values.filterBindings).length > 0) {
    valueConfig.filterBindings = values.filterBindings;
  }
  if (values.chartThemeMode && values.chartThemeMode !== 'default') {
    valueConfig.chartThemeMode = values.chartThemeMode;
  }
  if (values.chartType && VALUE_FORMAT_CHART_TYPES.has(values.chartType)) {
    applyValueFormatFields(valueConfig, values);
  }
  if (values.chartType === 'single') {
    valueConfig.compare = !!values.compare;
    valueConfig.compareMode = values.compareMode || 'percent';
    valueConfig.selectedFields = values.selectedFields;
    valueConfig.thresholdColors = values.thresholdColors;
  }
  if (values.chartType === 'gauge') {
    valueConfig.selectedFields = values.selectedFields;
    valueConfig.thresholdColors = values.thresholdColors;
    if (values.gaugeMin !== undefined) valueConfig.gaugeMin = values.gaugeMin;
    if (values.gaugeMax !== undefined) valueConfig.gaugeMax = values.gaugeMax;
    if (values.gaugeShape !== undefined) valueConfig.gaugeShape = values.gaugeShape;
  }
  if (values.chartType === 'multiValue') {
    if (values.thresholdColors?.length) {
      valueConfig.thresholdColors = values.thresholdColors;
    }
    if (values.valueMappings?.length) {
      valueConfig.valueMappings = values.valueMappings;
    }
  }
  if (
    (values.chartType === 'table' || values.chartType === 'eventTable') &&
    values.tableConfig
  ) {
    valueConfig.tableConfig = values.tableConfig;
  }
  if (values.chartType === 'topN') {
    applyTopNValueConfig(valueConfig, values);
  }
  if (values.chartType === 'nodeGraph') {
    const identityMode = values.nodeGraphIdentityMode || 'ip';
    valueConfig.nodeGraphIdentityMode = identityMode;
    valueConfig.nodeGraphSourceField = values.nodeGraphSourceField;
    valueConfig.nodeGraphTargetField = values.nodeGraphTargetField;
    valueConfig.nodeGraphValueField = values.nodeGraphValueField;
    if (identityMode === 'service') {
      valueConfig.nodeGraphTargetPortField = values.nodeGraphTargetPortField;
    }
  }
  if (values.interaction) {
    valueConfig.interaction = values.interaction;
  }
  return valueConfig;
};
