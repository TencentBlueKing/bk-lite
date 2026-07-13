import { useCallback, useMemo, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { buildDefaultFilterBindings } from '@/app/ops-analysis/utils/widgetDataTransform';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  FilterValue,
  UnifiedFilterDefinition,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import type {
  DropPosition,
  NodeConfigFormValues,
  NodeType,
  NodeTypeId,
  TopologyNodeData,
  ViewConfigFormValues,
} from '@/app/ops-analysis/types/topology';
import type { useTopologyState } from './useTopologyState';

const DEFAULT_DROP_POSITION: DropPosition = { x: 300, y: 200 };

interface PostMutationPayload {
  definitions: UnifiedFilterDefinition[];
  appliedValues: Record<string, FilterValue>;
  dataSources: DatasourceItem[];
  namespaceId: number | undefined;
}

interface UseTopologyNodeConfigControllerParams {
  state: ReturnType<typeof useTopologyState>;
  t: (key: string) => string;
  dataSources: DatasourceItem[];
  definitions: UnifiedFilterDefinition[];
  appliedFilterValues: Record<string, FilterValue>;
  appliedNamespaceId: number | undefined;
  addNewNode: (
    nodeConfig: TopologyNodeData,
    isSingleValue?: boolean,
  ) => string | null;
  handleAddChartNode: (
    values: ViewConfigFormValues,
    isNewNode?: boolean,
  ) => Promise<
    | {
        nodeId?: string;
        valueConfig?: ValueConfig;
      }
    | null
    | undefined
  >;
  handleNodeUpdate: (
    values: NodeConfigFormValues,
    filterValues?: Record<string, FilterValue>,
    definitions?: UnifiedFilterDefinition[],
    namespaceId?: number,
  ) => Promise<void>;
  handleViewConfigConfirm: (
    values: ViewConfigFormValues,
    filterValues?: Record<string, FilterValue>,
    definitions?: UnifiedFilterDefinition[],
    dataSources?: DatasourceItem[],
    namespaceId?: number,
  ) => void | Promise<void>;
  loadChartNodeData: (
    nodeId: string,
    valueConfig: ValueConfig,
    filterValues?: Record<string, FilterValue>,
    definitions?: UnifiedFilterDefinition[],
    dataSource?: DatasourceItem,
    namespaceId?: number,
  ) => void;
  scheduleTopologyPostMutation: (
    callback?: (payload: PostMutationPayload) => void,
  ) => void;
  updateSingleNodeData: (
    nodeConfig: TopologyNodeData,
    filterValues?: Record<string, FilterValue>,
    definitions?: UnifiedFilterDefinition[],
    namespaceId?: number,
  ) => void;
}

export const useNodeConfigFlow = ({
  state,
  t,
  dataSources,
  definitions,
  appliedFilterValues,
  appliedNamespaceId,
  addNewNode,
  handleAddChartNode,
  handleNodeUpdate,
  handleViewConfigConfirm,
  loadChartNodeData,
  scheduleTopologyPostMutation,
  updateSingleNodeData,
}: UseTopologyNodeConfigControllerParams) => {
  const [addNodeVisible, setAddNodeVisible] = useState(false);
  const [selectedNodeType, setSelectedNodeType] = useState<NodeType | null>(
    null,
  );
  const [dropPosition, setDropPosition] = useState<DropPosition | null>(null);
  const [viewSelectorVisible, setViewSelectorVisible] = useState(false);
  const [chartDropPosition, setChartDropPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);

  const handleShowNodeConfig = useCallback(
    (nodeType: NodeType, position?: DropPosition) => {
      setSelectedNodeType(nodeType);
      setDropPosition(position || DEFAULT_DROP_POSITION);
      setAddNodeVisible(true);
    },
    [],
  );

  const handleShowChartSelector = useCallback((position?: DropPosition) => {
    setChartDropPosition(position || DEFAULT_DROP_POSITION);
    setViewSelectorVisible(true);
  }, []);

  const handleChartSelectorConfirm = useCallback(
    (item: DatasourceItem) => {
      if (chartDropPosition) {
        const chartNodeData: TopologyNodeData = {
          type: 'chart',
          name: item.name,
          description: item.desc,
          position: chartDropPosition,
          isNewNode: true,
          valueConfig: {
            dataSource: item?.id,
            chartType: '',
            dataSourceParams: [],
          },
        };
        state.setEditingNodeData(chartNodeData);
        state.setViewConfigVisible(true);
      }
      setViewSelectorVisible(false);
      setChartDropPosition(null);
    },
    [chartDropPosition, state],
  );

  const handleChartSelectorCancel = useCallback(() => {
    setViewSelectorVisible(false);
    setChartDropPosition(null);
  }, []);

  const handleViewConfigClose = useCallback(() => {
    state.setViewConfigVisible(false);
    if (state.editingNodeData?.isNewNode) {
      state.setEditingNodeData(null);
    }
  }, [state]);

  const handleTopologyViewConfigConfirm = useCallback(
    async (values: ViewConfigFormValues) => {
      if (!state.editingNodeData) return;
      if (state.editingNodeData.isNewNode && state.editingNodeData.position) {
        const result = await handleAddChartNode(values, true);
        state.setEditingNodeData(null);
        state.setViewConfigVisible(false);

        scheduleTopologyPostMutation(
          ({
            definitions: newDefinitions,
            appliedValues: nextAppliedValues,
            dataSources: canvasDataSources,
            namespaceId: nextNamespaceId,
          }) => {
            if (result?.nodeId && result?.valueConfig?.dataSource) {
              const dataSource = canvasDataSources.find(
                (ds) => ds.id === result.valueConfig?.dataSource,
              );
              const nextValueConfig = {
                ...result.valueConfig,
                filterBindings: buildDefaultFilterBindings(
                  Array.isArray(result.valueConfig.dataSourceParams) &&
                    result.valueConfig.dataSourceParams.length > 0
                    ? result.valueConfig.dataSourceParams
                    : dataSource?.params,
                  newDefinitions,
                  result.valueConfig.filterBindings,
                ),
              };

              const addedNode = state.graphInstance?.getCellById(result.nodeId);
              if (addedNode) {
                const addedNodeData = addedNode.getData();
                addedNode.setData(
                  {
                    ...addedNodeData,
                    valueConfig: nextValueConfig,
                  },
                  { overwrite: true },
                );
              }

              loadChartNodeData(
                result.nodeId,
                nextValueConfig,
                nextAppliedValues,
                newDefinitions,
                dataSource,
                nextNamespaceId,
              );
            }
          },
        );
      } else {
        await handleViewConfigConfirm(
          values,
          appliedFilterValues,
          definitions,
          dataSources,
          appliedNamespaceId,
        );
        scheduleTopologyPostMutation();
      }
    },
    [
      appliedFilterValues,
      appliedNamespaceId,
      dataSources,
      definitions,
      handleAddChartNode,
      handleViewConfigConfirm,
      loadChartNodeData,
      scheduleTopologyPostMutation,
      state,
    ],
  );

  const handleNodeEditClose = useCallback(() => {
    if (addNodeVisible) {
      setAddNodeVisible(false);
      setSelectedNodeType(null);
      setDropPosition(null);
    } else {
      state.setNodeEditVisible(false);
      state.setEditingNodeData(null);
    }
  }, [addNodeVisible, state]);

  const handleNodeConfirm = useCallback(
    async (values: NodeConfigFormValues) => {
      if (addNodeVisible) {
        if (!selectedNodeType || !dropPosition) return;
        const nodeConfig: TopologyNodeData = {
          id: `node_${uuidv4()}`,
          type: selectedNodeType.id,
          name: values.name || selectedNodeType.name,
          unit: values.unit,
          conversionFactor: values.conversionFactor,
          decimalPlaces: values.decimalPlaces,
          position: dropPosition,
          logoType: values.logoType,
          logoIcon: values.logoIcon,
          logoUrl: values.logoUrl,
          valueConfig: {
            compare: !!values.compare,
            selectedFields: values.selectedFields || [],
            chartType: values.chartType,
            dataSource: values.dataSource,
            dataSourceParams: values.dataSourceParams || [],
            unitId: values.unitId || undefined,
            valueMappings: values.valueMappings || undefined,
          },
          styleConfig: {
            width: values.width,
            height: values.height,
            backgroundColor: values.backgroundColor,
            borderColor: values.borderColor,
            borderWidth: values.borderWidth,
            textColor: values.textColor,
            fontSize: values.fontSize,
            fontWeight: values.fontWeight,
            iconPadding: values.iconPadding,
            lineType: values.lineType,
            shapeType: values.shapeType,
            nameColor: values.nameColor,
            nameFontSize: values.nameFontSize,
            thresholdColors: values.thresholdColors,
          },
        };
        const isSingleValue =
          selectedNodeType.id === 'single-value' &&
          !!nodeConfig.valueConfig?.dataSource &&
          (nodeConfig.valueConfig?.selectedFields?.length ?? 0) > 0;
        const nodeId = addNewNode(nodeConfig, isSingleValue);
        scheduleTopologyPostMutation(
          ({
            definitions: newDefinitions,
            appliedValues: nextAppliedValues,
            namespaceId: nextNamespaceId,
          }) => {
            if (isSingleValue && nodeId) {
              updateSingleNodeData(
                { ...nodeConfig, id: nodeId },
                nextAppliedValues,
                newDefinitions,
                nextNamespaceId,
              );
            }
          },
        );
      } else {
        await handleNodeUpdate(
          values,
          appliedFilterValues,
          definitions,
          appliedNamespaceId,
        );
        scheduleTopologyPostMutation();
      }
      handleNodeEditClose();
    },
    [
      addNewNode,
      addNodeVisible,
      appliedFilterValues,
      appliedNamespaceId,
      definitions,
      dropPosition,
      handleNodeEditClose,
      handleNodeUpdate,
      scheduleTopologyPostMutation,
      selectedNodeType,
      updateSingleNodeData,
    ],
  );

  const nodeType = useMemo<NodeTypeId>(
    () =>
      addNodeVisible
        ? (selectedNodeType?.id as NodeTypeId)
        : (state.editingNodeData?.type as NodeTypeId),
    [addNodeVisible, selectedNodeType?.id, state.editingNodeData?.type],
  );

  const nodeTitle = useMemo(
    () =>
      state.isEditMode
        ? t('topology.nodeEditTitle')
        : t('topology.nodeViewTitle'),
    [state.isEditMode, t],
  );

  const nodeReadonly = addNodeVisible ? false : !state.isEditMode;

  return {
    addNodeVisible,
    handleChartSelectorCancel,
    handleChartSelectorConfirm,
    handleNodeConfirm,
    handleNodeEditClose,
    handleShowChartSelector,
    handleShowNodeConfig,
    handleTopologyViewConfigConfirm,
    handleViewConfigClose,
    nodeReadonly,
    nodeTitle,
    nodeType,
    viewSelectorVisible,
  };
};
