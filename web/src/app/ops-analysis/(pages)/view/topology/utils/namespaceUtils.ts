import type { Graph, Node } from '@antv/x6';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import type { LayoutItem, UnifiedFilterDefinition, FilterValue } from '@/app/ops-analysis/types/dashBoard';
import type { ViewConfigFormValues } from '@/app/ops-analysis/types/topology';
import {
  getFilterDefinitionId,
  getBindableFilterParams,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import dayjs from 'dayjs';

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

export const datasourceSupportsNamespace = (
  dataSource: DatasourceItem | undefined,
  namespaceId: number | undefined,
): boolean => {
  if (!dataSource || namespaceId === undefined) return true;
  if (!dataSource.namespaces || dataSource.namespaces.length === 0) return true;
  return dataSource.namespaces.includes(namespaceId);
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

  const discoveredParams = new Map<
    string,
    ParamItem & { type: 'string' | 'timeRange' }
  >();

  const nodes = graphInstance.getNodes();
  nodes.forEach((node: Node) => {
    const nodeData = node.getData();
    const nodeType = nodeData?.type;

    if (nodeType !== 'chart' && nodeType !== 'single-value' && nodeType !== 'table') {
      return;
    }

    const dataSourceId = nodeData?.valueConfig?.dataSource;
    const normalizedId = typeof dataSourceId === 'string' ? parseInt(dataSourceId, 10) : dataSourceId;
    const dataSource = dataSources.find((source) => source.id === normalizedId);
    const params = nodeData?.valueConfig?.dataSourceParams?.length
      ? nodeData.valueConfig.dataSourceParams
      : dataSource?.params;

    getBindableFilterParams(params).forEach((param) => {
      const id = getFilterDefinitionId(param.name, param.type);
      if (!discoveredParams.has(id)) {
        discoveredParams.set(id, param);
      }
    });
  });

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
        const end = dayjs();
        const start = end.subtract(param.value, 'minute');
        defaultValue = { start: start.toISOString(), end: end.toISOString(), selectValue: param.value };
      } else {
        defaultValue = param.value as FilterValue;
      }
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

/**
 * 同步筛选值与筛选定义：为缺失值的启用定义填充 defaultValue
 * 对于 timeRange 类型，如果 selectValue > 0，重新计算相对时间范围
 */
export const syncFilterValuesWithDefinitions = (
  nextDefinitions: UnifiedFilterDefinition[],
  currentValues: Record<string, FilterValue>,
): Record<string, FilterValue> => {
  const updatedValues = { ...currentValues };
  nextDefinitions.forEach((def) => {
    if (def.enabled && def.defaultValue !== null && def.defaultValue !== undefined) {
      if (updatedValues[def.id] === undefined || updatedValues[def.id] === null) {
        if (def.type === 'timeRange') {
          const rawValue = def.defaultValue as unknown as Record<string, unknown>;
          const selectValue = rawValue?.selectValue as number | undefined;
          if (selectValue && selectValue > 0) {
            const end = dayjs();
            const start = end.subtract(selectValue, 'minute');
            updatedValues[def.id] = {
              start: start.toISOString(),
              end: end.toISOString(),
              selectValue,
            };
          } else {
            updatedValues[def.id] = def.defaultValue;
          }
        } else {
          updatedValues[def.id] = def.defaultValue;
        }
      }
    }
  });
  return updatedValues;
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
  if (values.chartType === 'single') {
    valueConfig.compare = !!values.compare;
    valueConfig.selectedFields = values.selectedFields;
    valueConfig.thresholdColors = values.thresholdColors;
    if (values.unit !== undefined) valueConfig.unit = values.unit;
    if (values.conversionFactor !== undefined) valueConfig.conversionFactor = values.conversionFactor;
    if (values.decimalPlaces !== undefined) valueConfig.decimalPlaces = values.decimalPlaces;
  }
  if (values.chartType === 'gauge') {
    valueConfig.selectedFields = values.selectedFields;
    valueConfig.thresholdColors = values.thresholdColors;
    if (values.unit !== undefined) valueConfig.unit = values.unit;
    if (values.conversionFactor !== undefined) valueConfig.conversionFactor = values.conversionFactor;
    if (values.decimalPlaces !== undefined) valueConfig.decimalPlaces = values.decimalPlaces;
    if (values.gaugeMin !== undefined) valueConfig.gaugeMin = values.gaugeMin;
    if (values.gaugeMax !== undefined) valueConfig.gaugeMax = values.gaugeMax;
    if (values.gaugeShape !== undefined) valueConfig.gaugeShape = values.gaugeShape;
  }
  if (values.chartType === 'table' && values.tableConfig) {
    valueConfig.tableConfig = values.tableConfig;
  }
  if (values.chartType === 'topN') {
    valueConfig.topNLabelField = values.topNLabelField;
    valueConfig.topNValueField = values.topNValueField;
  }
  return valueConfig;
};
