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
import { Select } from 'antd';
import { useTopologyState } from './hooks/useTopologyState';
import { useGraphOperations } from './hooks/useGraphOperations';
import { useContextMenuAndModal } from './hooks/useGraphInteractions';
import { useTopologyResources } from './hooks/useTopologyResources';
import { useTopologyPresentation } from './hooks/useTopologyPresentation';
import { useTopologyRefresh } from './hooks/useTopologyRefresh';
import { useTopologyLifecycle } from './hooks/useTopologyLifecycle';
import { useNodeConfigFlow } from './hooks/useNodeConfigFlow';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useUnifiedFilter } from '@/app/ops-analysis/hooks/useUnifiedFilter';
import {
  TopologyProps,
  TopologyNodeData,
  TopologyPresentationConfig,
  TopologyRef,
  TopologyViewportConfig,
} from '@/app/ops-analysis/types/topology';
import type { FilterValue } from '@/app/ops-analysis/types/dashBoard';
import TopologyToolbar from './components/toolbar';
import TopologyCanvasShell from './components/canvasShell';
import TopologyPresentationModal from './components/presentationModal';
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
import {
  getOpsChartTheme,
  getOpsChartThemeByMode,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import { convertNodesToLayoutItems } from './utils/namespaceUtils';
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '@/app/ops-analysis/components/appFullscreen';
import {
  getTopologyViewportDraft,
  normalizeTopologyViewportConfig,
} from './utils/viewport';
import { createNodeByType } from './utils/registerNode';

const formatScreenClock = (date: Date) => {
  const weekday = new Intl.DateTimeFormat('zh-CN', {
    weekday: 'short',
  }).format(date);
  const day = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
  const time = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);

  return `${day} ${weekday} ${time}`;
};

type PresentationChromeConfig = NonNullable<TopologyPresentationConfig['chrome']>;

const SCREEN_TITLE_NODE_IDS = [
  'screen-title-frame',
  'screen-title-left-line',
  'screen-title-right-line',
  'screen-title',
];
const SCREEN_CLOCK_NODE_IDS = ['screen-clock'];

const DEFAULT_PRESENTATION_CHROME: PresentationChromeConfig = {
  title: '基础资源态势大屏',
  showTitle: true,
  showClock: true,
};

const CLEARED_PRESENTATION_CHROME: PresentationChromeConfig = {
  title: '',
  showTitle: false,
  showClock: false,
};

const buildDefaultScreenTitleNodes = (title: string): TopologyNodeData[] => [
  {
    id: 'screen-title-frame',
    type: 'basic-shape',
    name: '',
    presentationRole: 'decorative-frame',
    position: { x: 730, y: 22 },
    zIndex: 5,
    styleConfig: {
      width: 460,
      height: 58,
      backgroundColor: 'rgba(10, 49, 77, 0.72)',
      borderColor: 'rgba(125, 211, 252, 0.56)',
      borderWidth: 1,
      lineType: 'solid',
      shapeType: 'rectangle',
      renderEffect: 'glass',
    },
  },
  {
    id: 'screen-title-left-line',
    type: 'basic-shape',
    name: '',
    presentationRole: 'decorative-frame',
    position: { x: 590, y: 50 },
    zIndex: 4,
    styleConfig: {
      width: 140,
      height: 2,
      backgroundColor: 'rgba(34, 211, 238, 0.6)',
      borderColor: 'transparent',
      borderWidth: 0,
      lineType: 'solid',
      shapeType: 'rectangle',
      renderEffect: 'normal',
    },
  },
  {
    id: 'screen-title-right-line',
    type: 'basic-shape',
    name: '',
    presentationRole: 'decorative-frame',
    position: { x: 1190, y: 50 },
    zIndex: 4,
    styleConfig: {
      width: 140,
      height: 2,
      backgroundColor: 'rgba(34, 211, 238, 0.6)',
      borderColor: 'transparent',
      borderWidth: 0,
      lineType: 'solid',
      shapeType: 'rectangle',
      renderEffect: 'normal',
    },
  },
  {
    id: 'screen-title',
    type: 'text',
    name: title,
    presentationRole: 'screen-title',
    position: { x: 730, y: 22 },
    zIndex: 6,
    styleConfig: {
      width: 460,
      height: 58,
      backgroundColor: 'transparent',
      borderColor: 'transparent',
      textColor: '#EEFCFF',
      fontSize: 34,
      fontWeight: 800,
    },
  },
];

const buildDefaultScreenClockNode = (): TopologyNodeData => ({
  id: 'screen-clock',
  type: 'text',
  name: formatScreenClock(new Date()),
  presentationRole: 'screen-clock',
  position: { x: 1540, y: 38 },
  zIndex: 6,
  styleConfig: {
    width: 270,
    height: 34,
    backgroundColor: 'transparent',
    borderColor: 'transparent',
    textColor: '#7DD3FC',
    fontSize: 22,
    fontWeight: 700,
  },
});

const getScreenTitleFromGraph = (graph: any, fallbackTitle: string) => {
  const titleNode = graph?.getCellById?.('screen-title');
  const titleData = titleNode?.getData?.();
  const nodeText = titleNode?.getAttrByPath?.('label/text');
  return (
    titleData?.name ||
    (typeof nodeText === 'string' ? nodeText : '') ||
    fallbackTitle
  );
};

const hasScreenTitleNodes = (graph: any) =>
  SCREEN_TITLE_NODE_IDS.some((id) => Boolean(graph?.getCellById?.(id)));

const hasScreenClockNodes = (graph: any) =>
  SCREEN_CLOCK_NODE_IDS.some((id) => Boolean(graph?.getCellById?.(id)));

const isCanvasBackgroundEnabled = (
  config?: TopologyPresentationConfig | null,
) => config?.enableCanvasBackground ?? config?.theme === 'tech-blue';

const applyPresentationChromeNodes = (
  graph: any,
  chrome: PresentationChromeConfig,
  fallbackTitle: string,
) => {
  if (!graph) return;

  const title = (chrome.title || '').trim() || fallbackTitle;

  if (chrome.showTitle === false) {
    SCREEN_TITLE_NODE_IDS.forEach((id) => graph.getCellById?.(id)?.remove?.());
  } else {
    const titleNode = graph.getCellById?.('screen-title');
    if (titleNode) {
      const currentData = titleNode.getData?.() || {};
      titleNode.setData?.({ ...currentData, name: title }, { overwrite: true });
      titleNode.attr?.('label/text', title);
    } else {
      buildDefaultScreenTitleNodes(title).forEach((nodeConfig) => {
        graph.addNode?.(createNodeByType(nodeConfig));
      });
    }
  }

  if (!chrome.showClock) {
    SCREEN_CLOCK_NODE_IDS.forEach((id) => graph.getCellById?.(id)?.remove?.());
  } else if (!graph.getCellById?.('screen-clock')) {
    graph.addNode?.(createNodeByType(buildDefaultScreenClockNode()));
  }
};

const Topology = forwardRef<TopologyRef, TopologyProps>(
  ({ selectedTopology }, ref) => {
    const themeName = resolveOpsChartThemeName();
    const chartTheme = getOpsChartTheme(themeName);
    const screenDarkTheme = getOpsChartThemeByMode('screen-dark');
    const isDarkTheme = themeName === 'dark';
    const containerRef = useRef<HTMLDivElement>(null);
    const canvasContainerRef = useRef<HTMLDivElement>(null as any);
    const presentationHostRef = useRef<HTMLDivElement>(null as any);
    const minimapContainerRef = useRef<HTMLDivElement>(null as any);
    const refreshTimerRef = useRef<NodeJS.Timeout | null>(null);
    const resizeTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const [minimapVisible, setMinimapVisible] = useState(true);
    const [filterConfigModalVisible, setFilterConfigModalVisible] =
      useState(false);
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
    const [viewportConfig, setViewportConfig] =
      useState<TopologyViewportConfig>(() => getTopologyViewportDraft(null));
    const [presentationConfig, setPresentationConfig] =
      useState<TopologyPresentationConfig | null>(null);
    const [presentationChromeDraft, setPresentationChromeDraft] =
      useState<PresentationChromeConfig>(DEFAULT_PRESENTATION_CHROME);
    const [
      presentationCanvasBackgroundDraft,
      setPresentationCanvasBackgroundDraft,
    ] = useState(false);
    const rebuildFiltersRef = useRef<(() => void) | null>(null);
    const { isFullscreen, enterFullscreen, exitFullscreen } =
      useAppViewFullscreen();

    const { t } = useTranslation();
    const intl = useIntl();
    const state = useTopologyState();
    const dataSourceManager = useDataSourceManager();
    const { loadCanvasNamespaces } = useOpsAnalysis();

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
    const { namespaceOptions, syncTopologyCanvasResources } =
      useTopologyResources({
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

    const {
      clearRefreshTimer,
      handleFilterConfigConfirm,
      handleFilterSearch,
      handleFrequencyChange,
      handleRefresh,
      rebuildFiltersFromNodes,
      refreshTopologyNodes,
      scheduleTopologyInitialization,
      scheduleTopologyPostMutation,
    } = useTopologyRefresh({
      graphInstance: state.graphInstance,
      namespaceOptions,
      refreshTimerRef,
      dataSources: dataSourceManager.dataSources,
      definitions,
      filterValues,
      appliedFilterValues,
      appliedNamespaceId,
      namespaceDraftId,
      setAppliedFilterValues,
      setAppliedNamespaceId,
      setDefinitions,
      setFilterValues,
      setNamespaceDraftId,
      setNodeChangeKey,
      syncTopologyCanvasResources,
      refreshAllSingleValueNodes,
      refreshAllChartNodes,
      updateDefinitions,
    });

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

    const {
      activePresentationPresetKey,
      handleClearPresentationConfig: handleClearPresentationConfigBase,
      handleFullscreenToggle,
      handleOpenPresentationConfig: handleOpenPresentationConfigBase,
      handlePresentationConfigConfirm: handlePresentationConfigConfirmBase,
      handlePresentationDraftChange,
      handlePresentationPresetSelect,
      isLetterboxFullscreen,
      letterboxLayout,
      normalizedViewport,
      presentationConfigDraft,
      presentationConfigModalVisible,
      setPresentationConfigDraft,
      setPresentationConfigModalVisible,
      viewportGuideTransform,
    } = useTopologyPresentation({
      graphInstance: state.graphInstance,
      isEditMode: state.isEditMode,
      toggleEditMode,
      viewportConfig,
      setViewportConfig,
      containerRef,
      canvasContainerRef,
      presentationHostRef,
      resizeCanvas,
      handleCanvasResize,
      isFullscreen,
      enterFullscreen,
      exitFullscreen,
      t,
    });

    const handlePresentationChromeDraftChange = useCallback(
      (patch: Partial<PresentationChromeConfig>) => {
        setPresentationChromeDraft((prev) => ({
          ...prev,
          ...patch,
        }));
      },
      [],
    );

    const handleOpenPresentationConfig = useCallback(() => {
      const fallbackTitle =
        selectedTopology?.name || DEFAULT_PRESENTATION_CHROME.title;
      const currentChrome = presentationConfig?.chrome;
      const graph = state.graphInstance;
      const graphHasTitle = hasScreenTitleNodes(graph);
      const graphHasClock = hasScreenClockNodes(graph);

      setPresentationChromeDraft({
        title:
          currentChrome?.title ||
          getScreenTitleFromGraph(graph, fallbackTitle),
        showTitle: currentChrome?.showTitle ?? graphHasTitle,
        showClock: currentChrome?.showClock ?? graphHasClock,
      });
      setPresentationCanvasBackgroundDraft(
        isCanvasBackgroundEnabled(presentationConfig),
      );
      handleOpenPresentationConfigBase();
    }, [
      handleOpenPresentationConfigBase,
      presentationConfig,
      selectedTopology?.name,
      state.graphInstance,
    ]);

    const handlePresentationConfigConfirm = useCallback(() => {
      const hasAnyDimension = Boolean(
        presentationConfigDraft.width || presentationConfigDraft.height,
      );
      const hasCompleteDimension = Boolean(
        presentationConfigDraft.width && presentationConfigDraft.height,
      );
      if (hasAnyDimension && !hasCompleteDimension) {
        handlePresentationConfigConfirmBase();
        return;
      }

      const nextViewport = normalizeTopologyViewportConfig(presentationConfigDraft);

      handlePresentationConfigConfirmBase();
      const fallbackTitle =
        selectedTopology?.name || DEFAULT_PRESENTATION_CHROME.title;
      const nextChrome: PresentationChromeConfig = {
        title: (presentationChromeDraft.title || '').trim() || fallbackTitle,
        showTitle: presentationChromeDraft.showTitle !== false,
        showClock: Boolean(presentationChromeDraft.showClock),
      };

      applyPresentationChromeNodes(
        state.graphInstance,
        nextChrome,
        fallbackTitle,
      );
      const hasChromeConfig = nextChrome.showTitle || nextChrome.showClock;
      setPresentationConfig((prev) =>
        nextViewport || hasChromeConfig || presentationCanvasBackgroundDraft
          ? {
            ...(prev || {}),
            templateKey: prev?.templateKey || 'custom-screen',
            templateVersion: prev?.templateVersion || 1,
            theme: presentationCanvasBackgroundDraft ? 'tech-blue' : undefined,
            enableCanvasBackground: presentationCanvasBackgroundDraft,
            chrome: nextChrome,
          }
          : null,
      );
    }, [
      handlePresentationConfigConfirmBase,
      presentationChromeDraft,
      presentationCanvasBackgroundDraft,
      presentationConfigDraft,
      presentationConfigDraft.height,
      presentationConfigDraft.width,
      selectedTopology?.name,
      state.graphInstance,
    ]);

    const handlePresentationConfigDraftClear = useCallback(() => {
      handleClearPresentationConfigBase();
      setPresentationChromeDraft(CLEARED_PRESENTATION_CHROME);
      setPresentationCanvasBackgroundDraft(false);
    }, [handleClearPresentationConfigBase]);

    const {
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
    } = useNodeConfigFlow({
      state,
      t,
      dataSources: dataSourceManager.dataSources,
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
    });

    const handleSave = () => {
      if (selectedTopology) {
        handleSaveTopology(
          selectedTopology,
          definitions,
          normalizedViewport,
          presentationConfig,
        );
      }
    };

    useEffect(() => {
      rebuildFiltersRef.current = rebuildFiltersFromNodes;
    }, [rebuildFiltersFromNodes]);

    const hasUnsavedChanges = () => {
      return state.isEditMode;
    };

    useImperativeHandle(ref, () => ({
      hasUnsavedChanges,
    }));

    const { handleCancelEdit, handleEnterEditMode } = useTopologyLifecycle({
      selectedTopology,
      state,
      definitions,
      appliedFilterValues,
      appliedNamespaceId,
      presentationConfig,
      viewportConfig,
      setAppliedFilterValues,
      setAppliedNamespaceId,
      setDefinitions,
      setFilterValues,
      setNamespaceDraftId,
      setPresentationConfig,
      setViewportConfig,
      clearOperationHistory,
      clearRefreshTimer,
      finishInitialization,
      handleLoadTopology,
      loadCanvasNamespaces,
      refreshAllSingleValueNodes,
      refreshAllChartNodes,
      refreshTopologyNodes,
      scheduleTopologyInitialization,
      startInitialization,
      syncTopologyCanvasResources,
      toggleEditMode,
    });

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

    useEffect(() => {
      if (!state.graphInstance || !presentationConfig) return;

      const syncClockNodes = () => {
        const clockText = formatScreenClock(new Date());
        state.graphInstance?.getNodes().forEach((node) => {
          const nodeData = node.getData?.();
          if (
            node.id === 'screen-clock' ||
            nodeData?.presentationRole === 'screen-clock'
          ) {
            node.attr('label/text', clockText);
          }
        });
      };

      syncClockNodes();
      const timer = window.setInterval(syncClockNodes, 1000);
      return () => {
        window.clearInterval(timer);
      };
    }, [presentationConfig, state.graphInstance]);

    const NodePanel =
      nodeType === 'single-value' ? SingleValueNodePanel : ShapeNodePanel;

    const isTechBluePresentation = isCanvasBackgroundEnabled(presentationConfig);
    const panelStyle = {
      //   border: `1px solid ${chartTheme.panelBorderColor}`,
      background: isTechBluePresentation
        ? screenDarkTheme.screenCanvasBg
        : chartTheme.panelBg,
    };
    const topologyContainerStyle: React.CSSProperties = {
      backgroundColor: isTechBluePresentation
        ? '#02050d'
        : isDarkTheme ? 'var(--color-fill-1)' : '#f5f6f8',
      zIndex: isFullscreen ? 1100 : undefined,
    };

    return (
      <div
        className={`flex flex-col ${styles.topologyContainer} ${
          isTechBluePresentation ? styles.techBluePresentation : ''
        } ${
          isFullscreen
            ? 'fixed inset-0 h-screen w-screen overflow-hidden'
            : 'flex-1 overflow-auto p-2 pb-0'
        }`}
        style={topologyContainerStyle}
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
            boxShadow: isTechBluePresentation
              ? '0 0 0 1px rgba(45, 212, 255, 0.26), 0 22px 70px rgba(0, 0, 0, 0.42)'
              : isFullscreen
                ? 'none'
                : isDarkTheme
                  ? '0 10px 24px rgba(0, 0, 0, 0.18)'
                  : '0 12px 28px rgba(31, 63, 104, 0.06)',
          }}
        >
          {!presentationConfig && (definitions.length > 0 || namespaceSelectorElement) && (
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
            {!isFullscreen && (!presentationConfig || state.isEditMode) && (
              <NodeSidebar
                collapsed={state.collapsed}
                isEditMode={state.isEditMode}
                graphInstance={state.graphInstance ?? undefined}
                setCollapsed={state.setCollapsed}
                onShowNodeConfig={handleShowNodeConfig}
                onShowChartSelector={handleShowChartSelector}
              />
            )}

            <TopologyCanvasShell
              canvasContainerRef={canvasContainerRef}
              containerRef={containerRef}
              minimapContainerRef={minimapContainerRef}
              presentationHostRef={presentationHostRef}
              isFullscreen={isFullscreen}
              isLetterboxFullscreen={isLetterboxFullscreen}
              isEditMode={state.isEditMode}
              loading={loading}
              minimapVisible={minimapVisible}
              presentationMode={Boolean(presentationConfig)}
              normalizedViewport={normalizedViewport}
              letterboxLayout={letterboxLayout}
              panelStyle={panelStyle}
              viewportGuideTransform={viewportGuideTransform}
              t={t}
              setMinimapVisible={setMinimapVisible}
            />
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
          title={nodeTitle}
          nodeType={nodeType}
          readonly={nodeReadonly}
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
          showChartThemeMode={true}
        />

        <TopologyPresentationModal
          activePresetKey={activePresentationPresetKey}
          chromeDraft={presentationChromeDraft}
          draft={presentationConfigDraft}
          open={presentationConfigModalVisible}
          showCanvasBackground={presentationCanvasBackgroundDraft}
          t={t}
          onCancel={() => setPresentationConfigModalVisible(false)}
          onCanvasBackgroundChange={setPresentationCanvasBackgroundDraft}
          onChromeDraftChange={handlePresentationChromeDraftChange}
          onClear={handlePresentationConfigDraftClear}
          onConfirm={handlePresentationConfigConfirm}
          onDraftChange={handlePresentationDraftChange}
          onDraftColorChange={setPresentationConfigDraft}
          onPresetSelect={handlePresentationPresetSelect}
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
  },
);

Topology.displayName = 'Topology';

export default Topology;
