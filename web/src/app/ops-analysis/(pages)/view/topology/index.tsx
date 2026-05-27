import React, {
  useRef,
  useEffect,
  forwardRef,
  useImperativeHandle,
  useState,
  useCallback,
  useMemo,
} from 'react';
import { useIntl } from 'react-intl';
import styles from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { setLocaleData } from './utils/localeStore';
import { Spin, Select } from 'antd';
import { AppstoreOutlined, CloseOutlined } from '@ant-design/icons';
import { v4 as uuidv4 } from 'uuid';
import { useTopologyState } from './hooks/useTopologyState';
import { useGraphOperations } from './hooks/useGraphOperations';
import { useContextMenuAndModal } from './hooks/useGraphInteractions';
import { useTopologyResources } from './hooks/useTopologyResources';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useUnifiedFilter } from '@/app/ops-analysis/hooks/useUnifiedFilter';
import {
  NodeType,
  NodeTypeId,
  DropPosition,
  ViewConfigFormValues,
  NodeConfigFormValues,
  TopologyProps,
  TopologyRef,
  TopologyNodeData,
} from '@/app/ops-analysis/types/topology';
import type {
  UnifiedFilterDefinition,
  FilterValue,
} from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { Model } from '@antv/x6';
import TopologyToolbar from './components/toolbar';
import ContextMenu from './components/contextMenu';
import EdgeConfigPanel from './components/edgeConfPanel';
import NodeSidebar from './components/nodeSidebar';
import NodeConfPanel from './components/nodeConfPanel';
import ViewConfig from '../dashBoard/components/viewConfig';
import ViewSelector from '../dashBoard/components/viewSelector';
import {
  UnifiedFilterBar,
  UnifiedFilterConfigModal,
} from '@/app/ops-analysis/components/unifiedFilter';
import { buildDefaultFilterBindings } from '@/app/ops-analysis/utils/widgetDataTransform';
import {
  getOpsChartTheme,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import {
  convertNodesToLayoutItems,
  buildFiltersFromNodes,
  syncFilterValuesWithDefinitions,
} from './utils/namespaceUtils';
import {
  collectTopologyNamespaceIds,
} from '@/app/ops-analysis/utils/canvasResources';

const Topology = forwardRef<TopologyRef, TopologyProps>(
  ({ selectedTopology }, ref) => {
    const themeName = resolveOpsChartThemeName();
    const chartTheme = getOpsChartTheme(themeName);
    const isDarkTheme = themeName === 'dark';
    const containerRef = useRef<HTMLDivElement>(null);
    const canvasContainerRef = useRef<HTMLDivElement>(null as any);
    const minimapContainerRef = useRef<HTMLDivElement>(null as any);
    const refreshTimerRef = useRef<NodeJS.Timeout | null>(null);
    const resizeTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const [addNodeVisible, setAddNodeVisible] = useState(false);
    const [selectedNodeType, setSelectedNodeType] = useState<NodeType | null>(
      null
    );
    const [dropPosition, setDropPosition] = useState<DropPosition | null>(null);
    const [viewSelectorVisible, setViewSelectorVisible] = useState(false);
    const [chartDropPosition, setChartDropPosition] = useState<{
      x: number;
      y: number;
    } | null>(null);
    const [minimapVisible, setMinimapVisible] = useState(true);
    const [filterConfigModalVisible, setFilterConfigModalVisible] = useState(false);
    const [namespaceDraftId, setNamespaceDraftId] = useState<
      number | undefined
    >(undefined);
    const [appliedNamespaceId, setAppliedNamespaceId] = useState<
      number | undefined
    >(undefined);
    const [appliedFilterValues, setAppliedFilterValues] = useState<
      Record<string, FilterValue>
    >({});
    const [nodeChangeKey, setNodeChangeKey] = useState(0);
    const [originalGraphState, setOriginalGraphState] = useState<Model.FromJSONData | null>(null);
    const [originalDefinitions, setOriginalDefinitions] = useState<UnifiedFilterDefinition[]>([]);
    const rebuildFiltersRef = useRef<(() => void) | null>(null);

    const { t } = useTranslation();
    const intl = useIntl();
    const state = useTopologyState();
    const dataSourceManager = useDataSourceManager();
    const {
      loadCanvasNamespaces,
    } = useOpsAnalysis();

    const {
      definitions,
      filterValues,
      setFilterValues,
      updateDefinitions,
      setDefinitions,
    } = useUnifiedFilter();

    useEffect(() => {
      setLocaleData(intl.locale, intl.messages as Record<string, string>);
    }, [intl.locale, intl.messages]);

    const handleNodeRemovedCallback = useCallback(() => {
      rebuildFiltersRef.current?.();
    }, []);

    const {
      zoomIn,
      zoomOut,
      handleFit,
      handleDelete,
      addNewNode,
      handleNodeUpdate,
      handleViewConfigConfirm,
      handleAddChartNode,
      handleSaveTopology,
      handleLoadTopology,
      resizeCanvas,
      loading,
      toggleEditMode,
      undo,
      redo,
      canUndo,
      canRedo,
      startInitialization,
      finishInitialization,
      clearOperationHistory,
      refreshAllSingleValueNodes,
      refreshAllChartNodes,
      loadChartNodeData,
      updateSingleNodeData,
    } = useGraphOperations(containerRef, state, minimapContainerRef, handleNodeRemovedCallback);

    const { handleEdgeConfigConfirm, closeEdgeConfig, handleMenuClick } =
      useContextMenuAndModal(containerRef, state);
    const handleLoadTopologyRef = useRef(handleLoadTopology);

    useEffect(() => {
      handleLoadTopologyRef.current = handleLoadTopology;
    }, [handleLoadTopology]);
    const {
      namespaceOptions,
      syncTopologyCanvasResources,
    } = useTopologyResources({
      graphInstance: state.graphInstance,
      dataSources: dataSourceManager.dataSources,
      nodeChangeKey,
      namespaceDraftId,
      appliedNamespaceId,
      setNamespaceDraftId,
      setAppliedNamespaceId,
    });

    const namespaceSelectorElement = useMemo(() => {
      if (namespaceOptions.length <= 1) return undefined;
      return (
        <div className="flex items-center gap-2">
          <span className="text-sm text-(--color-text-2) whitespace-nowrap">
            {t('namespace.title')}:
          </span>
          <Select
            value={namespaceDraftId}
            onChange={(val: number) => {
              setNamespaceDraftId(val);
            }}
            options={namespaceOptions}
            style={{ minWidth: 160 }}
          />
        </div>
      );
    }, [namespaceOptions, namespaceDraftId, t]);

    const refreshTopologyNodes = useCallback(
      (
        scope:
          | 'filter-search'
          | 'namespace-search'
          | 'combined-search'
          | 'reload',
        nextValues = appliedFilterValues,
        nextDefinitions = definitions,
        nextNamespaceId = appliedNamespaceId,
      ) => {
        let shouldRefreshNode:
          | ((
              nodeData: TopologyNodeData,
              dataSource?: DatasourceItem,
            ) => boolean)
          | undefined;

        if (scope !== 'reload') {
          shouldRefreshNode = (
            nodeData: TopologyNodeData,
            dataSource?: DatasourceItem,
          ) => {
            const bindings = buildDefaultFilterBindings(
              nodeData.valueConfig?.dataSourceParams?.length
                ? nodeData.valueConfig.dataSourceParams
                : dataSource?.params,
              nextDefinitions,
              nodeData.valueConfig?.filterBindings,
            );
            const hasActiveFilterBinding = Boolean(
              bindings && Object.values(bindings).some((enabled) => enabled),
            );
            const usesNamespace = Boolean(
              Array.isArray(dataSource?.namespaces) &&
              dataSource.namespaces.length > 0,
            );

            if (scope === 'filter-search') {
              return hasActiveFilterBinding;
            }
            if (scope === 'namespace-search') {
              return usesNamespace;
            }

            return hasActiveFilterBinding || usesNamespace;
          };
        }

        refreshAllSingleValueNodes(
          nextValues,
          nextDefinitions,
          nextNamespaceId,
          dataSourceManager.dataSources,
          shouldRefreshNode,
        );
        refreshAllChartNodes(
          nextValues,
          nextDefinitions,
          dataSourceManager.dataSources,
          nextNamespaceId,
          shouldRefreshNode,
        );
      },
      [
        appliedFilterValues,
        definitions,
        appliedNamespaceId,
        refreshAllSingleValueNodes,
        refreshAllChartNodes,
        dataSourceManager.dataSources,
      ],
    );

    useEffect(() => {
      if (
        !state.graphInstance ||
        namespaceOptions.length === 0 ||
        appliedNamespaceId !== undefined
      ) {
        return;
      }

      const initialNamespaceId = namespaceOptions[0].value;
      setNamespaceDraftId(initialNamespaceId);
      setAppliedNamespaceId(initialNamespaceId);
      refreshTopologyNodes(
        'namespace-search',
        appliedFilterValues,
        definitions,
        initialNamespaceId,
      );
    }, [
      state.graphInstance,
      namespaceOptions,
      appliedNamespaceId,
      appliedFilterValues,
      definitions,
      refreshTopologyNodes,
    ]);

    const handleFrequencyChange = useCallback(
      (frequency: number) => {
        if (refreshTimerRef.current) {
          clearInterval(refreshTimerRef.current);
          refreshTimerRef.current = null;
        }

        if (frequency > 0) {
          refreshTimerRef.current = setInterval(() => {
            refreshTopologyNodes('reload');
          }, frequency);
        }
      },
      [refreshTopologyNodes],
    );

    const handleRefresh = useCallback(() => {
      setAppliedFilterValues(filterValues);
      setAppliedNamespaceId(namespaceDraftId);
      refreshTopologyNodes(
        'reload',
        filterValues,
        definitions,
        namespaceDraftId,
      );
    }, [filterValues, definitions, namespaceDraftId, refreshTopologyNodes]);

    // 监听画布容器大小变化，自动调整画布大小
    const handleCanvasResize = useCallback(() => {
      if (resizeCanvas && canvasContainerRef.current) {
        // 稍微延迟以确保DOM已经更新
        setTimeout(() => {
          if (canvasContainerRef.current) {
            const rect = canvasContainerRef.current.getBoundingClientRect();
            resizeCanvas(rect.width, rect.height);
          }
        }, 100);
      }
    }, [resizeCanvas]);

    useEffect(() => {
      if (!canvasContainerRef.current) return;

      const resizeObserver = new ResizeObserver(() => {
        if (resizeTimeoutRef.current) {
          clearTimeout(resizeTimeoutRef.current);
        }
        resizeTimeoutRef.current = setTimeout(() => {
          handleCanvasResize();
        }, 150);
      });

      resizeObserver.observe(canvasContainerRef.current);

      return () => {
        resizeObserver.disconnect();
        if (resizeTimeoutRef.current) {
          clearTimeout(resizeTimeoutRef.current);
          resizeTimeoutRef.current = null;
        }
      };
    }, [handleCanvasResize]);

    useEffect(() => {
      handleCanvasResize();
    }, [state.collapsed]);

    const handleShowNodeConfig = (
      nodeType: NodeType,
      position?: DropPosition
    ) => {
      setSelectedNodeType(nodeType);
      setDropPosition(position || { x: 300, y: 200 });
      setAddNodeVisible(true);
    };

    const handleShowChartSelector = (position?: DropPosition) => {
      setChartDropPosition(position || { x: 300, y: 200 });
      setViewSelectorVisible(true);
    };

    const handleChartSelectorConfirm = (item: DatasourceItem) => {
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
    };

    const handleChartSelectorCancel = () => {
      setViewSelectorVisible(false);
      setChartDropPosition(null);
    };

    const handleViewConfigClose = () => {
      state.setViewConfigVisible(false);
      if (state.editingNodeData?.isNewNode) {
        state.setEditingNodeData(null);
      }
    };

    const handleTopologyViewConfigConfirm = async (
      values: ViewConfigFormValues
    ) => {
      if (!state.editingNodeData) return;
      if (state.editingNodeData.isNewNode && state.editingNodeData.position) {
        const result = await handleAddChartNode(values, true);
        state.setEditingNodeData(null);
        state.setViewConfigVisible(false);

        scheduleTopologyPostMutation(({
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
        });
      } else {
        await handleViewConfigConfirm(
          values,
          appliedFilterValues,
          definitions,
          dataSourceManager.dataSources,
          appliedNamespaceId,
        );
        scheduleTopologyPostMutation();
      }
    };

    const handleNodeEditClose = () => {
      if (addNodeVisible) {
        setAddNodeVisible(false);
        setSelectedNodeType(null);
        setDropPosition(null);
      } else {
        state.setNodeEditVisible(false);
        state.setEditingNodeData(null);
      }
    };

    const handleNodeConfirm = async (values: NodeConfigFormValues) => {
      if (addNodeVisible) {
        if (!selectedNodeType || !dropPosition) return;
        const nodeConfig = {
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
            selectedFields: values.selectedFields || [],
            chartType: values.chartType,
            dataSource: values.dataSource,
            dataSourceParams: values.dataSourceParams || [],
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
            renderEffect: values.renderEffect,
            iconPadding: values.iconPadding,
            lineType: values.lineType,
            shapeType: values.shapeType,
            nameColor: values.nameColor,
            nameFontSize: values.nameFontSize,
            thresholdColors: values.thresholdColors,
          },
        };
        const isSingleValue = selectedNodeType.id === 'single-value' &&
          !!nodeConfig.valueConfig?.dataSource && (nodeConfig.valueConfig?.selectedFields?.length ?? 0) > 0;
        const nodeId = addNewNode(nodeConfig, isSingleValue);
        scheduleTopologyPostMutation(({
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
        });
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
    };

    const getNodeType = (): NodeTypeId => {
      return addNodeVisible
        ? (selectedNodeType?.id as NodeTypeId)
        : (state.editingNodeData?.type as NodeTypeId);
    };

    const getNodeTitle = (): string => {
      return state.isEditMode
        ? t('topology.nodeEditTitle')
        : t('topology.nodeViewTitle');
    };

    const getNodeReadonly = (): boolean => {
      return addNodeVisible ? false : !state.isEditMode;
    };

    const handleSave = () => {
      if (selectedTopology) {
        handleSaveTopology(selectedTopology, definitions);
      }
    };

    const handleEnterEditMode = useCallback(() => {
      if (state.graphInstance) {
        setOriginalGraphState(state.graphInstance.toJSON());
        setOriginalDefinitions([...definitions]);
      }
      toggleEditMode();
    }, [state.graphInstance, definitions, toggleEditMode]);

    const handleCancelEdit = useCallback(() => {
      if (state.graphInstance && originalGraphState) {
        state.graphInstance.fromJSON(originalGraphState);
      }
      const restoredDefs = [...originalDefinitions];
      const restoredValues = syncFilterValuesWithDefinitions(
        restoredDefs,
        appliedFilterValues,
      );
      setDefinitions(restoredDefs);
      setFilterValues(restoredValues);
      setAppliedFilterValues(restoredValues);
      toggleEditMode();
      refreshTopologyNodes(
        'reload',
        restoredValues,
        restoredDefs,
        appliedNamespaceId,
      );
    }, [
      state.graphInstance,
      originalGraphState,
      originalDefinitions,
      appliedFilterValues,
      appliedNamespaceId,
      setDefinitions,
      setFilterValues,
      toggleEditMode,
      refreshTopologyNodes,
    ]);

    const handleFilterValuesChange = useCallback((values: Record<string, FilterValue>) => {
      setFilterValues(values);
    }, [setFilterValues]);

    const handleFilterSearch = useCallback(
      (values: Record<string, FilterValue>) => {
        const namespaceChanged = namespaceDraftId !== appliedNamespaceId;
        setFilterValues(values);
        setAppliedFilterValues(values);
        setAppliedNamespaceId(namespaceDraftId);
        refreshTopologyNodes(
          namespaceChanged ? 'combined-search' : 'filter-search',
          values,
          definitions,
          namespaceDraftId,
        );
      },
      [
        namespaceDraftId,
        appliedNamespaceId,
        definitions,
        refreshTopologyNodes,
        setFilterValues,
      ],
    );

    const handleFilterReset = useCallback(
      (values: Record<string, FilterValue>) => {
        handleFilterSearch(values);
      },
      [handleFilterSearch],
    );

    const handleFilterConfigConfirm = useCallback(
      (newDefinitions: UnifiedFilterDefinition[]) => {
        updateDefinitions(newDefinitions);
        setFilterValues(
          syncFilterValuesWithDefinitions(newDefinitions, filterValues),
        );
        setAppliedFilterValues((prev) =>
          syncFilterValuesWithDefinitions(newDefinitions, prev),
        );
      },
      [updateDefinitions, filterValues, setFilterValues],
    );

    const resolveTopologyNamespaceId = useCallback((
      canvasDataSources: DatasourceItem[],
    ) => {
      if (namespaceDraftId !== undefined) {
        return namespaceDraftId;
      }
      if (appliedNamespaceId !== undefined) {
        return appliedNamespaceId;
      }

      const namespaceIds = Array.from(
        collectTopologyNamespaceIds(state.graphInstance, canvasDataSources),
      );
      return namespaceIds[0];
    }, [appliedNamespaceId, namespaceDraftId, state.graphInstance]);

    const scheduleTopologyPostMutation = useCallback((
      callback?: (payload: {
        definitions: UnifiedFilterDefinition[];
        appliedValues: Record<string, FilterValue>;
        dataSources: DatasourceItem[];
        namespaceId: number | undefined;
      }) => void,
    ) => {
      setTimeout(() => {
        const newDefinitions = buildFiltersFromNodes(
          state.graphInstance,
          dataSourceManager.dataSources,
          definitions,
        );
        const syncedValues = syncFilterValuesWithDefinitions(newDefinitions, filterValues);
        const nextAppliedValues = syncFilterValuesWithDefinitions(
          newDefinitions,
          appliedFilterValues,
        );

        setDefinitions(newDefinitions);
        setFilterValues(syncedValues);
        setAppliedFilterValues(nextAppliedValues);
        setNodeChangeKey((prev) => prev + 1);
        void syncTopologyCanvasResources().then((canvasDataSources) => {
          callback?.({
            definitions: newDefinitions,
            appliedValues: nextAppliedValues,
            dataSources: canvasDataSources,
            namespaceId: resolveTopologyNamespaceId(canvasDataSources),
          });
        });
      }, 100);
    }, [
      appliedFilterValues,
      dataSourceManager.dataSources,
      definitions,
      filterValues,
      resolveTopologyNamespaceId,
      setDefinitions,
      setFilterValues,
      syncTopologyCanvasResources,
      state.graphInstance,
    ]);

    const scheduleTopologyInitialization = useCallback((
      callback: () => void,
    ) => {
      setTimeout(callback, 100);
    }, []);

    const rebuildFiltersFromNodes = useCallback(() => {
      scheduleTopologyPostMutation();
    }, [scheduleTopologyPostMutation]);

    useEffect(() => {
      rebuildFiltersRef.current = rebuildFiltersFromNodes;
    }, [rebuildFiltersFromNodes]);

    const hasUnsavedChanges = () => {
      return state.isEditMode;
    };

    useImperativeHandle(ref, () => ({
      hasUnsavedChanges,
    }));

    useEffect(() => {
      state.resetAllStates();
      startInitialization();
      clearOperationHistory();
      setDefinitions([]);
      setFilterValues({});
      setAppliedFilterValues({});
      setOriginalDefinitions([]);
      setNamespaceDraftId(undefined);
      setAppliedNamespaceId(undefined);

      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }

      if (selectedTopology?.data_id && state.graphInstance) {
        handleLoadTopologyRef.current(selectedTopology.data_id).then(async (loadedFilters) => {
          const canvasDataSources = await syncTopologyCanvasResources();
          const autoBuiltFilters = buildFiltersFromNodes(
            state.graphInstance,
            canvasDataSources,
            loadedFilters
          );

          // Step 1: Build filter definitions and sync values
          const syncedValues = syncFilterValuesWithDefinitions(autoBuiltFilters, {});
          if (autoBuiltFilters.length > 0) {
            setDefinitions(autoBuiltFilters);
            setFilterValues(syncedValues);
            setAppliedFilterValues(syncedValues);
            setOriginalDefinitions([...autoBuiltFilters]);
          }

          // Step 2: Determine initial namespace
          const namespaceIds = Array.from(
            collectTopologyNamespaceIds(
              state.graphInstance,
              canvasDataSources,
            ),
          );
          const initialNamespaceId = namespaceIds.length > 0 ? namespaceIds[0] : undefined;
          setNamespaceDraftId(initialNamespaceId);
          setAppliedNamespaceId(initialNamespaceId);

          // Step 3: Fetch all node data with correct filter values
          scheduleTopologyInitialization(() => {
            refreshAllSingleValueNodes(syncedValues, autoBuiltFilters, initialNamespaceId);
            refreshAllChartNodes(syncedValues, autoBuiltFilters, canvasDataSources, initialNamespaceId);
            finishInitialization();
          });
        });
      } else if (!selectedTopology?.data_id && state.graphInstance) {
        void loadCanvasNamespaces([]);
        scheduleTopologyInitialization(() => {
          finishInitialization();
        });
      }

      return () => {
        if (refreshTimerRef.current) {
          clearInterval(refreshTimerRef.current);
          refreshTimerRef.current = null;
        }
      };
    }, [selectedTopology?.data_id, state.graphInstance, loadCanvasNamespaces, scheduleTopologyInitialization, syncTopologyCanvasResources]);

    const handleSelectMode = () => {
      state.setIsSelectMode(!state.isSelectMode);
      if (state.graphInstance) {
        state.graphInstance.enableSelection();
      }
    };

    // 键盘快捷键监听
    useEffect(() => {
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.ctrlKey || e.metaKey) {
          if (e.key === 'z' && !e.shiftKey) {
            e.preventDefault();
            undo();
          } else if (e.key === 'y' || (e.key === 'z' && e.shiftKey)) {
            e.preventDefault();
            redo();
          }
        }
      };

      document.addEventListener('keydown', handleKeyDown);
      return () => {
        document.removeEventListener('keydown', handleKeyDown);
      };
    }, [undo, redo]);

    return (
      <div
        className={`flex-1 p-2 pb-0 overflow-auto flex flex-col ${styles.topologyContainer}`}
        style={{
          backgroundColor: isDarkTheme ? 'var(--color-fill-1)' : '#f5f6f8',
        }}
      >
        {/* 工具栏 */}
        <TopologyToolbar
          selectedTopology={selectedTopology}
          onEdit={handleEnterEditMode}
          onSave={handleSave}
          onCancel={handleCancelEdit}
          onFilterConfig={() => setFilterConfigModalVisible(true)}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onFit={handleFit}
          onDelete={handleDelete}
          onSelectMode={handleSelectMode}
          onUndo={undo}
          onRedo={redo}
          canUndo={canUndo}
          canRedo={canRedo}
          isSelectMode={state.isSelectMode}
          isEditMode={state.isEditMode}
          onRefresh={handleRefresh}
          onFrequencyChange={handleFrequencyChange}
        />

        <div
          className="flex-1 rounded-2xl overflow-hidden flex flex-col"
          style={{
            border: `1px solid ${chartTheme.panelBorderColor}`,
            backgroundColor: chartTheme.panelBg,
            boxShadow: isDarkTheme
              ? '0 10px 24px rgba(0, 0, 0, 0.18)'
              : '0 12px 28px rgba(31, 63, 104, 0.06)',
          }}
        >
          {(definitions.length > 0 || namespaceSelectorElement) && (
            <div className="shrink-0">
              <UnifiedFilterBar
                definitions={definitions}
                values={filterValues}
                onChange={handleFilterValuesChange}
                onSearch={handleFilterSearch}
                onReset={handleFilterReset}
                prefixContent={namespaceSelectorElement}
                containerClassName="mx-0 mt-0"
                appearance="embedded"
              />
            </div>
          )}

          <div
            className={`flex-1 flex overflow-hidden p-2.5 ${state.collapsed ? 'gap-0' : 'gap-2'}`}
          >
            {/* 侧边栏 */}
            <NodeSidebar
              collapsed={state.collapsed}
              isEditMode={state.isEditMode}
              graphInstance={state.graphInstance ?? undefined}
              setCollapsed={state.setCollapsed}
              onShowNodeConfig={handleShowNodeConfig}
              onShowChartSelector={handleShowChartSelector}
            />

            {/* 画布容器 */}
            <div
              ref={canvasContainerRef}
              className="flex-1 relative rounded-xl overflow-hidden"
              style={{
                border: `1px solid ${chartTheme.panelBorderColor}`,
                backgroundColor: chartTheme.panelBg,
              }}
            >
              {loading && (
                <div
                  className="absolute inset-0 flex items-center justify-center backdrop-blur-sm z-10"
                  style={{
                    backgroundColor: 'var(--color-bg-1)',
                    opacity: 0.8,
                  }}
                >
                  <Spin size="large" />
                </div>
              )}
              <div
                ref={containerRef}
                className="absolute inset-0"
                tabIndex={-1}
              />

              <div
                className={styles.minimapContainer}
                style={{ display: minimapVisible ? 'block' : 'none' }}
              >
                <div className={styles.minimapHeader}>
                  <button
                    onClick={() => setMinimapVisible(false)}
                    className={styles.minimapCloseBtn}
                    title={t('topology.minimapCollapse')}
                  >
                    <CloseOutlined />
                  </button>
                </div>
                <div
                  ref={minimapContainerRef}
                  className={styles.minimapContent}
                />
              </div>
              {!minimapVisible && (
                <button
                  onClick={() => setMinimapVisible(true)}
                  className={styles.minimapShowBtn}
                  title={t('topology.minimapShow')}
                >
                  <AppstoreOutlined />
                </button>
              )}
            </div>
          </div>
        </div>

        <ContextMenu
          visible={state.contextMenuVisible}
          position={state.contextMenuPosition}
          targetType={state.contextMenuTargetType}
          onMenuClick={handleMenuClick}
          isEditMode={state.isEditMode}
        />

        <EdgeConfigPanel
          visible={state.edgeConfigVisible}
          readonly={!state.isEditMode}
          onClose={closeEdgeConfig}
          edgeData={state.currentEdgeData}
          onConfirm={handleEdgeConfigConfirm}
        />

        <NodeConfPanel
          visible={state.nodeEditVisible || addNodeVisible}
          title={getNodeTitle()}
          nodeType={getNodeType()}
          readonly={getNodeReadonly()}
          builtinNamespaceId={namespaceDraftId}
          editingNodeData={addNodeVisible ? null : state.editingNodeData}
          onClose={handleNodeEditClose}
          onConfirm={handleNodeConfirm}
          onCancel={handleNodeEditClose}
        />

        <ViewSelector
          visible={viewSelectorVisible}
          onOpenConfig={handleChartSelectorConfirm}
          onCancel={handleChartSelectorCancel}
        />

        <ViewConfig
          open={state.viewConfigVisible}
          item={state.editingNodeData}
          onClose={handleViewConfigClose}
          onConfirm={handleTopologyViewConfigConfirm}
          builtinNamespaceId={namespaceDraftId}
          dataSourceManager={dataSourceManager}
          filterDefinitions={definitions}
          unifiedFilterValues={filterValues}
        />

        <UnifiedFilterConfigModal
          open={filterConfigModalVisible}
          definitions={definitions}
          onConfirm={handleFilterConfigConfirm}
          onCancel={() => setFilterConfigModalVisible(false)}
          layoutItems={convertNodesToLayoutItems(state.graphInstance)}
          dataSources={dataSourceManager.dataSources}
        />
      </div>
    );
  }
);

Topology.displayName = 'Topology';

export default Topology;
