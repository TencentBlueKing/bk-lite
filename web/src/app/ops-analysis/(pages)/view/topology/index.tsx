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
import { Button, InputNumber, Modal, Select, Spin, message } from 'antd';
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
  TopologyViewportConfig,
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
import ShapeNodePanel from './components/shapeNodePanel';
import SingleValueNodePanel from './components/singleValueNodePanel';
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
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '../components/appFullscreen';
import {
  buildTopologyLetterboxLayout,
  getTopologyViewportDraft,
  normalizeTopologyViewportConfig,
} from './utils/viewport';

const DEFAULT_DROP_POSITION: DropPosition = { x: 300, y: 200 };

const PRESENTATION_PRESETS = [
  { key: '1366x768', width: 1366, height: 768, label: '1366 x 768' },
  { key: '1600x900', width: 1600, height: 900, label: '1600 x 900' },
  { key: '1920x1080', width: 1920, height: 1080, label: '1920 x 1080' },
  { key: '2560x1440', width: 2560, height: 1440, label: '2560 x 1440' },
];

const Topology = forwardRef<TopologyRef, TopologyProps>(
  ({ selectedTopology }, ref) => {
    const themeName = resolveOpsChartThemeName();
    const chartTheme = getOpsChartTheme(themeName);
    const isDarkTheme = themeName === 'dark';
    const containerRef = useRef<HTMLDivElement>(null);
    const canvasContainerRef = useRef<HTMLDivElement>(null as any);
    const presentationHostRef = useRef<HTMLDivElement>(null as any);
    const minimapContainerRef = useRef<HTMLDivElement>(null as any);
    const refreshTimerRef = useRef<NodeJS.Timeout | null>(null);
    const resizeTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const fullscreenViewportSnapshotRef = useRef<{
      zoom: number;
      tx: number;
      ty: number;
    } | null>(null);
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
    const [viewportConfig, setViewportConfig] =
      useState<TopologyViewportConfig>(() => getTopologyViewportDraft(null));
    const [presentationConfigModalVisible, setPresentationConfigModalVisible] =
      useState(false);
    const [presentationConfigDraft, setPresentationConfigDraft] =
      useState<TopologyViewportConfig>(() => getTopologyViewportDraft(null));
    const [originalViewportConfig, setOriginalViewportConfig] =
      useState<TopologyViewportConfig>(() => getTopologyViewportDraft(null));
    const [viewportGuideTransform, setViewportGuideTransform] = useState('');
    const [presentationBounds, setPresentationBounds] = useState({
      width: 0,
      height: 0,
    });
    const rebuildFiltersRef = useRef<(() => void) | null>(null);
    const resumeEditModeAfterFullscreenRef = useRef(false);
    const { isFullscreen, enterFullscreen, exitFullscreen } =
      useAppViewFullscreen();
    const normalizedViewport = useMemo(
      () => normalizeTopologyViewportConfig(viewportConfig),
      [viewportConfig],
    );
    const isLetterboxFullscreen = isFullscreen && Boolean(normalizedViewport);
    const letterboxLayout = useMemo(
      () =>
        buildTopologyLetterboxLayout(
          presentationBounds.width,
          presentationBounds.height,
          normalizedViewport,
        ),
      [normalizedViewport, presentationBounds.height, presentationBounds.width],
    );
    const activePresentationPresetKey = useMemo(
      () =>
        PRESENTATION_PRESETS.find(
          (preset) =>
            preset.width === presentationConfigDraft.width &&
            preset.height === presentationConfigDraft.height,
        )?.key,
      [presentationConfigDraft.height, presentationConfigDraft.width],
    );

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
    } = useGraphOperations(
      containerRef,
      state,
      minimapContainerRef,
      handleNodeRemovedCallback,
      isFullscreen,
    );

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

    const clearRefreshTimer = useCallback(() => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    }, []);

    const handleFrequencyChange = useCallback(
      (frequency: number) => {
        clearRefreshTimer();

        if (frequency > 0) {
          refreshTimerRef.current = setInterval(() => {
            refreshTopologyNodes('reload');
          }, frequency);
        }
      },
      [clearRefreshTimer, refreshTopologyNodes],
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
            resizeCanvas(
              canvasContainerRef.current.clientWidth,
              canvasContainerRef.current.clientHeight,
            );
          }
        }, 100);
      }
    }, [resizeCanvas]);

    useEffect(() => {
      if (!presentationHostRef.current || !isLetterboxFullscreen) {
        return;
      }

      const updateBounds = () => {
        if (!presentationHostRef.current) {
          return;
        }
        setPresentationBounds({
          width: presentationHostRef.current.clientWidth,
          height: presentationHostRef.current.clientHeight,
        });
      };

      updateBounds();

      const observer = new ResizeObserver(updateBounds);
      observer.observe(presentationHostRef.current);

      return () => {
        observer.disconnect();
      };
    }, [isLetterboxFullscreen]);

    useEffect(() => {
      if (!normalizedViewport || !containerRef.current) {
        setViewportGuideTransform('');
        return;
      }

      const viewportElement = containerRef.current.querySelector(
        '.x6-graph-svg-viewport',
      );

      if (!(viewportElement instanceof SVGGElement)) {
        setViewportGuideTransform('');
        return;
      }

      const syncTransform = () => {
        setViewportGuideTransform(
          viewportElement.getAttribute('transform') || '',
        );
      };

      syncTransform();

      const observer = new MutationObserver(syncTransform);
      observer.observe(viewportElement, {
        attributes: true,
        attributeFilter: ['transform'],
      });

      return () => {
        observer.disconnect();
      };
    }, [normalizedViewport, state.graphInstance]);

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
      setDropPosition(position || DEFAULT_DROP_POSITION);
      setAddNodeVisible(true);
    };

    const handleShowChartSelector = (position?: DropPosition) => {
      setChartDropPosition(position || DEFAULT_DROP_POSITION);
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
            compare: !!values.compare,
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
        handleSaveTopology(selectedTopology, definitions, normalizedViewport);
      }
    };

    const handleOpenPresentationConfig = useCallback(() => {
      setPresentationConfigDraft(getTopologyViewportDraft(viewportConfig));
      setPresentationConfigModalVisible(true);
    }, [viewportConfig]);

    const handlePresentationPresetSelect = useCallback(
      (preset: { width: number; height: number }) => {
        setPresentationConfigDraft(
          getTopologyViewportDraft({
            width: preset.width,
            height: preset.height,
          }),
        );
      },
      [],
    );

    const handlePresentationDraftChange = useCallback(
      (patch: { width?: number; height?: number }) => {
        setPresentationConfigDraft((prev) => ({
          ...prev,
          ...patch,
        }));
      },
      [],
    );

    const handleClearPresentationConfig = useCallback(() => {
      setPresentationConfigDraft(getTopologyViewportDraft(null));
    }, []);

    const handlePresentationConfigConfirm = useCallback(() => {
      const hasAnyDimension = Boolean(
        presentationConfigDraft.width || presentationConfigDraft.height,
      );
      const nextViewport = normalizeTopologyViewportConfig(
        presentationConfigDraft,
      );

      if (hasAnyDimension && !nextViewport) {
        message.warning(t('topology.fixedResolutionIncomplete'));
        return;
      }

      setViewportConfig(getTopologyViewportDraft(nextViewport));
      setPresentationConfigModalVisible(false);
    }, [presentationConfigDraft, t]);

    const handleEnterEditMode = useCallback(() => {
      if (state.graphInstance) {
        setOriginalGraphState(state.graphInstance.toJSON());
        setOriginalDefinitions([...definitions]);
        setOriginalViewportConfig(getTopologyViewportDraft(viewportConfig));
      }
      toggleEditMode();
    }, [state.graphInstance, definitions, toggleEditMode, viewportConfig]);

    useEffect(() => {
      if (isFullscreen || !resumeEditModeAfterFullscreenRef.current) {
        return;
      }

      resumeEditModeAfterFullscreenRef.current = false;
      if (!state.isEditMode) {
        toggleEditMode();
      }
    }, [isFullscreen, state.isEditMode, toggleEditMode]);

    const handleFullscreenToggle = useCallback(() => {
      if (isFullscreen) {
        exitFullscreen();
        return;
      }

      resumeEditModeAfterFullscreenRef.current = state.isEditMode;
      if (state.isEditMode) {
        toggleEditMode();
      }
      enterFullscreen();
    }, [
      enterFullscreen,
      exitFullscreen,
      isFullscreen,
      state.isEditMode,
      toggleEditMode,
    ]);

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
      setViewportConfig(getTopologyViewportDraft(originalViewportConfig));
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
      originalViewportConfig,
      setDefinitions,
      setFilterValues,
      toggleEditMode,
      refreshTopologyNodes,
    ]);

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
      setViewportConfig(getTopologyViewportDraft(null));
      setOriginalViewportConfig(getTopologyViewportDraft(null));
      setNamespaceDraftId(undefined);
      setAppliedNamespaceId(undefined);

      clearRefreshTimer();

      if (selectedTopology?.data_id && state.graphInstance) {
        handleLoadTopologyRef
          .current(selectedTopology.data_id)
          .then(async ({ filters: loadedFilters, viewport }) => {
            const loadedViewport = getTopologyViewportDraft(viewport);
            setViewportConfig(loadedViewport);
            setOriginalViewportConfig(loadedViewport);
            const canvasDataSources = await syncTopologyCanvasResources();
            const autoBuiltFilters = buildFiltersFromNodes(
              state.graphInstance,
              canvasDataSources,
              loadedFilters,
            );

            // Step 1: Build filter definitions and sync values
            const syncedValues = syncFilterValuesWithDefinitions(
              autoBuiltFilters,
              {},
            );
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
            const initialNamespaceId =
              namespaceIds.length > 0 ? namespaceIds[0] : undefined;
            setNamespaceDraftId(initialNamespaceId);
            setAppliedNamespaceId(initialNamespaceId);

            // Step 3: Fetch all node data with correct filter values
            scheduleTopologyInitialization(() => {
              refreshAllSingleValueNodes(
                syncedValues,
                autoBuiltFilters,
                initialNamespaceId,
              );
              refreshAllChartNodes(
                syncedValues,
                autoBuiltFilters,
                canvasDataSources,
                initialNamespaceId,
              );
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
        clearRefreshTimer();
      };
    }, [
      selectedTopology?.data_id,
      state.graphInstance,
      loadCanvasNamespaces,
      scheduleTopologyInitialization,
      syncTopologyCanvasResources,
    ]);

    useEffect(() => {
      const graph = state.graphInstance as any;

      if (!graph) {
        return;
      }

      if (isLetterboxFullscreen && normalizedViewport) {
        if (!letterboxLayout) {
          return;
        }

        if (!fullscreenViewportSnapshotRef.current) {
          const translation =
            typeof graph.translate === 'function' ? graph.translate() : null;

          fullscreenViewportSnapshotRef.current = {
            zoom: typeof graph.zoom === 'function' ? graph.zoom() : 1,
            tx: typeof translation?.tx === 'number' ? translation.tx : 0,
            ty: typeof translation?.ty === 'number' ? translation.ty : 0,
          };
        }

        resizeCanvas(
          Math.round(letterboxLayout.renderedWidth),
          Math.round(letterboxLayout.renderedHeight),
        );

        if (typeof graph.zoom === 'function') {
          graph.zoom(letterboxLayout.scale, { absolute: true });
        }
        if (typeof graph.translate === 'function') {
          graph.translate(0, 0);
        }
        return;
      }

      if (fullscreenViewportSnapshotRef.current) {
        const snapshot = fullscreenViewportSnapshotRef.current;
        if (typeof graph.zoom === 'function') {
          graph.zoom(snapshot.zoom, { absolute: true });
        }
        if (typeof graph.translate === 'function') {
          graph.translate(snapshot.tx, snapshot.ty);
        }
        fullscreenViewportSnapshotRef.current = null;
      }

      handleCanvasResize();
    }, [
      handleCanvasResize,
      isLetterboxFullscreen,
      letterboxLayout,
      normalizedViewport,
      resizeCanvas,
      state.graphInstance,
    ]);

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

    const NodePanel = getNodeType() === 'single-value' ? SingleValueNodePanel : ShapeNodePanel;

    const panelStyle = {
      border: `1px solid ${chartTheme.panelBorderColor}`,
      backgroundColor: chartTheme.panelBg,
    };

    const viewportGuideOverlay =
      state.isEditMode && normalizedViewport && !isLetterboxFullscreen ? (
        <div
          className="absolute inset-0"
          style={{ pointerEvents: 'none', zIndex: 5 }}
        >
          <svg className="h-full w-full overflow-visible">
            <g transform={viewportGuideTransform || undefined}>
              <rect
                x={0}
                y={0}
                width={normalizedViewport.width}
                height={normalizedViewport.height}
                fill="none"
                stroke="rgba(46, 99, 255, 0.78)"
                strokeDasharray="10 8"
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
              />
            </g>
          </svg>
        </div>
      ) : null;

    const canvasInnerContent = (
      <>
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
        {viewportGuideOverlay}
        <div ref={containerRef} className="absolute inset-0" tabIndex={-1} />

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
          <div ref={minimapContainerRef} className={styles.minimapContent} />
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
      </>
    );

    return (
      <div
        className={`flex flex-col ${styles.topologyContainer} ${
          isFullscreen
            ? 'fixed inset-0 h-screen w-screen overflow-hidden'
            : 'flex-1 overflow-auto p-2 pb-0'
        }`}
        style={{
          backgroundColor: isDarkTheme ? 'var(--color-fill-1)' : '#f5f6f8',
          zIndex: isFullscreen ? 1100 : undefined,
        }}
      >
        <AppViewFullscreenExit visible={isFullscreen} onExit={exitFullscreen} />
        {/* 工具栏 */}
        {!isFullscreen && (
          <TopologyToolbar
            selectedTopology={selectedTopology}
            onEdit={handleEnterEditMode}
            onSave={handleSave}
            onCancel={handleCancelEdit}
            onFilterConfig={() => setFilterConfigModalVisible(true)}
            onPresentationConfig={handleOpenPresentationConfig}
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
            isFullscreen={isFullscreen}
            onFullscreenToggle={handleFullscreenToggle}
            onRefresh={handleRefresh}
            onFrequencyChange={handleFrequencyChange}
          />
        )}

        <div
          className={`flex-1 overflow-hidden flex flex-col ${
            isFullscreen ? 'rounded-none' : 'rounded-2xl'
          }`}
          style={{
            ...panelStyle,
            boxShadow: isFullscreen
              ? 'none'
              : isDarkTheme
                ? '0 10px 24px rgba(0, 0, 0, 0.18)'
                : '0 12px 28px rgba(31, 63, 104, 0.06)',
          }}
        >
          {(definitions.length > 0 || namespaceSelectorElement) && (
            <div className="shrink-0">
              <UnifiedFilterBar
                definitions={definitions}
                values={filterValues}
                onChange={setFilterValues}
                onSearch={handleFilterSearch}
                onReset={handleFilterSearch}
                prefixContent={namespaceSelectorElement}
                containerClassName="mx-0 mt-0"
                appearance="embedded"
                popupZIndex={isFullscreen ? 1200 : undefined}
              />
            </div>
          )}

          <div
            className={`flex-1 flex overflow-hidden ${
              isFullscreen ? 'p-0' : 'p-2.5'
            } ${state.collapsed ? 'gap-0' : 'gap-2'}`}
          >
            {/* 侧边栏 */}
            {!isFullscreen && (
              <NodeSidebar
                collapsed={state.collapsed}
                isEditMode={state.isEditMode}
                graphInstance={state.graphInstance ?? undefined}
                setCollapsed={state.setCollapsed}
                onShowNodeConfig={handleShowNodeConfig}
                onShowChartSelector={handleShowChartSelector}
              />
            )}

            {/* 画布容器 */}
            <div
              ref={presentationHostRef}
              className={`flex-1 overflow-hidden ${
                isLetterboxFullscreen
                  ? 'flex items-center justify-center'
                  : 'relative'
              }`}
              style={
                isLetterboxFullscreen && normalizedViewport
                  ? {
                      backgroundColor:
                        normalizedViewport.letterboxColor || '#000000',
                    }
                  : undefined
              }
            >
              <div
                className={
                  isLetterboxFullscreen
                    ? 'relative shrink-0 overflow-hidden'
                    : 'h-full w-full'
                }
                style={
                  isLetterboxFullscreen && normalizedViewport
                    ? {
                        width:
                          letterboxLayout?.renderedWidth ||
                          normalizedViewport.width,
                        height:
                          letterboxLayout?.renderedHeight ||
                          normalizedViewport.height,
                      }
                    : undefined
                }
              >
                <div
                  ref={canvasContainerRef}
                  className={`relative overflow-hidden ${
                    isLetterboxFullscreen ? '' : 'h-full w-full'
                  } ${isFullscreen ? 'rounded-none' : 'rounded-xl'}`}
                  style={{
                    ...panelStyle,
                    ...(isLetterboxFullscreen && normalizedViewport
                      ? {
                          width:
                            letterboxLayout?.renderedWidth ||
                            normalizedViewport.width,
                          height:
                            letterboxLayout?.renderedHeight ||
                            normalizedViewport.height,
                        }
                      : {}),
                  }}
                >
                  {canvasInnerContent}
                </div>
              </div>
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

        <NodePanel
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

        <Modal
          open={presentationConfigModalVisible}
          centered
          title={t('topology.presentationConfig')}
          onCancel={() => setPresentationConfigModalVisible(false)}
          footer={[
            <Button key="clear" onClick={handleClearPresentationConfig}>
              {t('topology.clearPresentationConfig')}
            </Button>,
            <Button
              key="cancel"
              onClick={() => setPresentationConfigModalVisible(false)}
            >
              {t('common.cancel')}
            </Button>,
            <Button
              key="confirm"
              type="primary"
              onClick={handlePresentationConfigConfirm}
            >
              {t('common.confirm')}
            </Button>,
          ]}
        >
          <div className="space-y-4 pt-1">
            <div>
              <div className="mb-2 text-sm font-medium text-(--color-text-1)">
                {t('topology.commonResolutions')}
              </div>
              <div className="flex flex-wrap gap-2">
                {PRESENTATION_PRESETS.map((preset) => (
                  <Button
                    key={preset.key}
                    type={
                      activePresentationPresetKey === preset.key
                        ? 'primary'
                        : 'default'
                    }
                    onClick={() => handlePresentationPresetSelect(preset)}
                    className="rounded-full!"
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="mb-1 text-sm text-(--color-text-2)">
                  {t('topology.fixedResolutionWidth')}
                </div>
                <InputNumber
                  min={1}
                  precision={0}
                  controls={false}
                  value={presentationConfigDraft.width}
                  placeholder="1920"
                  className="w-full"
                  onChange={(value) =>
                    handlePresentationDraftChange({
                      width: typeof value === 'number' ? value : undefined,
                    })
                  }
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-(--color-text-2)">
                  {t('topology.fixedResolutionHeight')}
                </div>
                <InputNumber
                  min={1}
                  precision={0}
                  controls={false}
                  value={presentationConfigDraft.height}
                  placeholder="1080"
                  className="w-full"
                  onChange={(value) =>
                    handlePresentationDraftChange({
                      height: typeof value === 'number' ? value : undefined,
                    })
                  }
                />
              </div>
            </div>
          </div>
        </Modal>

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
