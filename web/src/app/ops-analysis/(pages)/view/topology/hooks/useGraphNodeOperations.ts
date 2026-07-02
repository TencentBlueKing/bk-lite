import { useCallback } from 'react';
import type { Node, Graph as X6Graph } from '@antv/x6';
import { v4 as uuidv4 } from 'uuid';
import { buildDefaultFilterBindings } from '@/app/ops-analysis/utils/widgetDataTransform';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type {
  NodeStyleConfig,
  NodeConfigFormValues,
  TopologyNodeData,
  ViewConfigFormValues,
} from '@/app/ops-analysis/types/topology';
import {
  extractComparableValue,
  fetchCompareData,
  getChangePercent,
  toComparableNumber,
} from '@/app/ops-analysis/utils/compareQuery';
import { useTranslation } from '@/utils/i18n';
import { buildValueConfig } from '../utils/namespaceUtils';
import { createNodeByType, updateNodeAttributes } from '../utils/registerNode';
import { getColorByThreshold } from '../utils/thresholdUtils';
import { formatUnit } from '@/app/ops-analysis/utils/unitFormat';
import { applyValueMapping } from '@/app/ops-analysis/utils/valueMapping';
import {
  adjustSingleValueNodeSize,
  formatDisplayValue,
} from '../utils/topologyUtils';
import { useGraphData } from './useGraphData';
import type { useTopologyState } from './useTopologyState';

const LOADING_ANIMATION_INTERVAL = 300;

function formatNumericValue(
  rawValue: unknown,
  conversionFactor?: number,
  decimalPlaces?: number,
): string {
  const numericValue =
    typeof rawValue === 'string' ? parseFloat(rawValue) : rawValue;

  if (typeof numericValue === 'number' && !isNaN(numericValue)) {
    const factor = conversionFactor !== undefined ? conversionFactor : 1;
    const places = decimalPlaces !== undefined ? decimalPlaces : 2;
    return parseFloat((numericValue * factor).toFixed(places)).toString();
  }

  return formatDisplayValue(rawValue, undefined, undefined, conversionFactor);
}

function buildCompareSuffix(
  compareLabel: string,
  changePercent: number | null,
): string {
  if (changePercent === null) {
    return ` (${compareLabel} --)`;
  }
  const arrow = changePercent > 0 ? '↑' : changePercent < 0 ? '↓' : '';
  return ` (${compareLabel} ${arrow}${Math.abs(changePercent).toFixed(1)}%)`;
}

function mergeStyleConfig(
  values: NodeConfigFormValues,
  existing: NodeStyleConfig | undefined,
  keys: Array<keyof NodeStyleConfig>,
): NodeStyleConfig {
  let result: NodeStyleConfig = {};
  for (const key of keys) {
    const nextValue = values[key] !== undefined ? values[key] : existing?.[key];
    if (nextValue !== undefined) {
      result = {
        ...result,
        [key]: nextValue,
      };
    }
  }
  return result;
}

interface UseGraphNodeOperationsParams {
  graphInstance: X6Graph | null;
  state: ReturnType<typeof useTopologyState>;
  handleSave: () => void;
}

export const useGraphNodeOperations = ({
  graphInstance,
  state,
  handleSave,
}: UseGraphNodeOperationsParams) => {
  const { t } = useTranslation();
  const { getSourceDataByApiId } = useDataSourceApi();

  const startLoadingAnimation = useCallback((node: Node) => {
    const loadingStates = ['○ ○ ○', '● ○ ○', '○ ● ○', '○ ○ ●', '○ ○ ○'];
    let currentIndex = 0;

    const updateLoading = () => {
      const nodeData = node.getData();
      if (!nodeData?.isLoading) {
        return;
      }

      const currentLoadingText = loadingStates[currentIndex];
      node.setAttrByPath('label/text', currentLoadingText);

      adjustSingleValueNodeSize(node, currentLoadingText, 80);

      currentIndex = (currentIndex + 1) % loadingStates.length;

      setTimeout(updateLoading, LOADING_ANIMATION_INTERVAL);
    };

    setTimeout(updateLoading, LOADING_ANIMATION_INTERVAL);
  }, []);

  const updateSingleNodeData = useCallback(
    async (
      nodeConfig: TopologyNodeData,
      unifiedFilterValues?: Record<string, FilterValue>,
      filterDefinitions?: UnifiedFilterDefinition[],
      namespaceId?: number,
    ) => {
      if (!nodeConfig || !graphInstance || !nodeConfig.id) return;

      const node = graphInstance.getCellById(nodeConfig.id);
      const { valueConfig } = nodeConfig || {};
      if (!node) return;

      if (
        nodeConfig.type !== 'single-value' ||
        !valueConfig?.dataSource ||
        !valueConfig?.selectedFields?.length
      ) {
        return;
      }

      node.setData(
        { ...node.getData(), isLoading: true, hasError: false },
        { overwrite: true },
      );
      if (node.isNode()) {
        startLoadingAnimation(node as Node);
      }

      try {
        const effectiveFilterBindings =
          valueConfig.filterBindings ||
          buildDefaultFilterBindings(
            valueConfig.dataSourceParams || [],
            filterDefinitions || [],
            undefined,
          );

        const compareResult = await fetchCompareData({
          dataSourceId: Number(valueConfig.dataSource),
          getSourceDataByApiId,
          config: valueConfig,
          dataSource: { params: valueConfig.dataSourceParams || [] },
          extraParams:
            namespaceId !== undefined
              ? { namespace_id: namespaceId }
              : undefined,
          unifiedFilterValues,
          filterBindings: effectiveFilterBindings,
          filterDefinitions,
        });

        const dataToExtract = compareResult.currentData;
        if (!dataToExtract) {
          throw new Error(t('topology.noData'));
        }

        const field = valueConfig.selectedFields[0];
        const value = extractComparableValue(dataToExtract, field);
        const baselineValue = extractComparableValue(
          compareResult.baselineData,
          field,
        );
        const changePercent = valueConfig.compare
          ? getChangePercent(
            toComparableNumber(value),
            toComparableNumber(baselineValue),
          )
          : null;

        // 值映射优先；其次结构化单位库自动量纲；最后回退到原数值+自由文本单位
        const valueMapping = applyValueMapping(value, valueConfig.valueMappings);
        let displayValue: string;
        if (valueMapping?.text !== undefined) {
          displayValue = valueMapping.text;
        } else if (valueConfig.unitId) {
          displayValue = formatUnit(value as number | string | null, valueConfig.unitId, {
            decimals: nodeConfig.decimalPlaces,
            conversionFactor: nodeConfig.conversionFactor,
          }).text;
        } else {
          displayValue = formatNumericValue(
            value,
            nodeConfig.conversionFactor,
            nodeConfig.decimalPlaces,
          );
          if (nodeConfig.unit?.trim()) {
            displayValue = `${displayValue} ${nodeConfig.unit}`;
          }
        }

        const compareSuffix = valueConfig.compare
          ? buildCompareSuffix(
            t('dashboard.comparePreviousShortLabel'),
            changePercent,
          )
          : '';
        const nodeText = `${displayValue}${compareSuffix}`;

        let textColor = nodeConfig.styleConfig?.textColor;
        if (nodeConfig.styleConfig?.thresholdColors?.length) {
          const numValue =
            typeof value === 'string'
              ? parseFloat(value)
              : typeof value === 'number'
                ? value
                : null;
          textColor = getColorByThreshold(
            numValue,
            nodeConfig.styleConfig.thresholdColors,
            nodeConfig.styleConfig.textColor,
          );
        }
        // 值映射命中颜色时覆盖阈值/默认色
        if (valueMapping?.color) {
          textColor = valueMapping.color;
        }

        node.setData(
          { ...node.getData(), isLoading: false, hasError: false },
          { overwrite: true },
        );
        node.setAttrByPath('label/text', nodeText);
        node.setAttrByPath('label/fill', textColor);

        if (node.isNode()) {
          adjustSingleValueNodeSize(node, nodeText);
        }
      } catch (error) {
        console.error('更新单值节点数据失败:', error);
        node.setData(
          { ...node.getData(), isLoading: false, hasError: true },
          { overwrite: true },
        );
        node.setAttrByPath('label/text', '--');
        if (node.isNode()) {
          adjustSingleValueNodeSize(node, '--');
        }
      }
    },
    [graphInstance, getSourceDataByApiId, startLoadingAnimation, t],
  );

  const dataOperations = useGraphData(
    graphInstance,
    updateSingleNodeData,
    startLoadingAnimation,
    handleSave,
  );

  const addNewNode = useCallback(
    (nodeConfig: TopologyNodeData, skipInitialFetch?: boolean) => {
      if (!graphInstance) {
        return null;
      }
      const nodeData = createNodeByType(nodeConfig);
      const { valueConfig } = nodeConfig || {};
      const addedNode = graphInstance.addNode(nodeData);
      if (nodeConfig.type === 'single-value') {
        adjustSingleValueNodeSize(addedNode, nodeConfig.name || '');
      }
      if (
        !skipInitialFetch &&
        nodeConfig.type === 'single-value' &&
        valueConfig?.dataSource &&
        valueConfig?.selectedFields?.length
      ) {
        startLoadingAnimation(addedNode);
        updateSingleNodeData({ ...nodeConfig, id: addedNode.id });
      } else if (
        skipInitialFetch &&
        nodeConfig.type === 'single-value' &&
        valueConfig?.dataSource &&
        valueConfig?.selectedFields?.length
      ) {
        startLoadingAnimation(addedNode);
      }
      return addedNode.id;
    },
    [graphInstance, updateSingleNodeData, startLoadingAnimation],
  );

  function getUpdatedNodeConfig(
    editingNode: TopologyNodeData,
    values: NodeConfigFormValues,
  ): TopologyNodeData {
    const { valueConfig, styleConfig } = editingNode || {};
    return {
      id: editingNode.id,
      type: editingNode.type,
      name: values.name,
      unit: values.unit,
      conversionFactor: values.conversionFactor,
      decimalPlaces: values.decimalPlaces,
      description: values.description,
      position: editingNode.position,
      logoType: values.logoType || editingNode.logoType,
      logoIcon: values.logoIcon || editingNode.logoIcon,
      logoUrl: values.logoUrl || editingNode.logoUrl,
      valueConfig: {
        compare: values.compare ?? valueConfig?.compare,
        selectedFields: values.selectedFields || valueConfig?.selectedFields,
        chartType: values.chartType || valueConfig?.chartType,
        dataSource: values.dataSource || valueConfig?.dataSource,
        dataSourceParams:
          values.dataSourceParams || valueConfig?.dataSourceParams,
        topNLabelField: values.topNLabelField ?? valueConfig?.topNLabelField,
        topNValueField: values.topNValueField ?? valueConfig?.topNValueField,
        unitId: values.unitId ?? valueConfig?.unitId,
        valueMappings: values.valueMappings ?? valueConfig?.valueMappings,
      },
      styleConfig: mergeStyleConfig(values, styleConfig, [
        'textColor',
        'fontSize',
        'fontWeight',
        'backgroundColor',
        'borderColor',
        'borderWidth',
        'iconPadding',
        'width',
        'height',
        'lineType',
        'shapeType',
        'nameColor',
        'nameFontSize',
        'thresholdColors',
      ]),
    } as TopologyNodeData;
  }

  const handleNodeUpdate = useCallback(
    async (
      values: NodeConfigFormValues,
      unifiedFilterValues?: Record<string, FilterValue>,
      filterDefinitions?: UnifiedFilterDefinition[],
      namespaceId?: number,
    ) => {
      if (!values) return;
      const editingNode = state.editingNodeData;
      if (!editingNode || !graphInstance) return;
      try {
        const updatedConfig = getUpdatedNodeConfig(editingNode, values);
        if (!updatedConfig.id) return;
        const node = graphInstance.getCellById(updatedConfig.id);
        if (!node || !node.isNode()) return;
        updateNodeAttributes(node as Node, updatedConfig);
        if (
          updatedConfig.type === 'single-value' &&
          updatedConfig.valueConfig?.dataSource &&
          updatedConfig.valueConfig?.selectedFields?.length
        ) {
          node.setData(
            { ...node.getData(), isLoading: true, hasError: false },
            { overwrite: true },
          );
          startLoadingAnimation(node as Node);
          updateSingleNodeData(
            updatedConfig,
            unifiedFilterValues,
            filterDefinitions,
            namespaceId,
          );
        }
        state.setNodeEditVisible(false);
        state.setEditingNodeData(null);
      } catch (error) {
        console.error('节点更新失败:', error);
      }
    },
    [graphInstance, updateSingleNodeData, state, startLoadingAnimation],
  );

  const handleViewConfigConfirm = useCallback(
    (
      values: ViewConfigFormValues,
      unifiedFilterValues?: Record<string, FilterValue>,
      filterDefinitions?: UnifiedFilterDefinition[],
      dataSources?: DatasourceItem[],
      namespaceId?: number,
    ) => {
      if (state.editingNodeData && graphInstance) {
        const node = graphInstance.getCellById(state.editingNodeData.id);
        if (node) {
          const valueConfig = buildValueConfig(values);
          const updatedData = {
            ...state.editingNodeData,
            name: values.name,
            valueConfig,
            isLoading: !!values.dataSource,
            hasError: false,
          };
          node.setData(updatedData, { overwrite: true });

          if (state.editingNodeData.type === 'chart' && values.dataSource) {
            const dataSource = dataSources?.find(
              (ds) => ds.id === values.dataSource,
            );
            dataOperations.loadChartNodeData(
              state.editingNodeData.id,
              updatedData.valueConfig,
              unifiedFilterValues,
              filterDefinitions,
              dataSource,
              namespaceId,
            );
          }
        }
      }
      state.setViewConfigVisible(false);
    },
    [graphInstance, state, dataOperations],
  );

  const handleAddChartNode = useCallback(
    async (values: ViewConfigFormValues, skipInitialFetch?: boolean) => {
      if (!graphInstance) {
        return null;
      }
      const valueConfig = buildValueConfig(values, true);
      const nodeConfig: TopologyNodeData = {
        id: `node_${uuidv4()}`,
        type: 'chart',
        name: values.name,
        description: values.description || '',
        position: state.editingNodeData.position,
        styleConfig: {},
        valueConfig,
      };
      const nodeId = addNewNode(nodeConfig);
      if (!skipInitialFetch && nodeConfig.valueConfig?.dataSource && nodeId) {
        dataOperations.loadChartNodeData(nodeId, nodeConfig.valueConfig);
      }
      return { nodeId, valueConfig: nodeConfig.valueConfig };
    },
    [graphInstance, addNewNode, dataOperations],
  );

  const handleNodeEditClose = useCallback(() => {
    state.setNodeEditVisible(false);
    state.setEditingNodeData(null);
  }, [state]);

  const refreshAllSingleValueNodes = useCallback(
    (
      unifiedFilterValues?: Record<string, FilterValue>,
      filterDefinitions?: UnifiedFilterDefinition[],
      namespaceId?: number,
      dataSources?: DatasourceItem[],
      shouldRefreshNode?: (
        nodeData: TopologyNodeData,
        dataSource?: DatasourceItem,
      ) => boolean,
    ) => {
      if (!graphInstance) return;

      const nodes = graphInstance.getNodes();
      nodes.forEach((node: Node) => {
        const nodeData = node.getData();
        if (
          nodeData.type === 'single-value' &&
          nodeData.valueConfig?.dataSource &&
          nodeData.valueConfig?.selectedFields?.length
        ) {
          const dataSource = dataSources?.find(
            (source) => source.id === nodeData.valueConfig.dataSource,
          );
          if (shouldRefreshNode && !shouldRefreshNode(nodeData, dataSource)) {
            return;
          }
          updateSingleNodeData(
            nodeData,
            unifiedFilterValues,
            filterDefinitions,
            namespaceId,
          );
        }
      });
    },
    [graphInstance, updateSingleNodeData],
  );

  return {
    addNewNode,
    handleAddChartNode,
    handleNodeEditClose,
    handleNodeUpdate,
    handleViewConfigConfirm,
    refreshAllSingleValueNodes,
    startLoadingAnimation,
    updateSingleNodeData,
    ...dataOperations,
  };
};
