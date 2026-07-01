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
import { useTopologyRefresh } from './hooks/useTopologyRefresh';
import { useTopologyLifecycle } from './hooks/useTopologyLifecycle';
import { useNodeConfigFlow } from './hooks/useNodeConfigFlow';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useUnifiedFilter } from '@/app/ops-analysis/hooks/useUnifiedFilter';
import {
  TopologyProps,
  TopologyRef,
} from '@/app/ops-analysis/types/topology';
import type { FilterValue } from '@/app/ops-analysis/types/dashBoard';
import TopologyToolbar from './components/toolbar';
import TopologyCanvasShell from './components/canvasShell';
import ContextMenu from './components/contextMenu';
import EdgeConfigPanel from './components/edgeConfPanel';
import NodeSidebar from './components/nodeSidebar';
import ShapeNodePanel from './components/shapeNodePanel';
import SingleValueNodePanel from './components/singleValueNodePanel';
import ViewConfig from '@/app/ops-analysis/components/widgetConfig';
import ViewSelector from '@/app/ops-analysis/components/widgetSelector';
import {
  UnifiedFilterBar,
  UnifiedFilterConfigModal,
} from '@/app/ops-analysis/components/unifiedFilter';
import {
  getOpsChartTheme,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import { convertNodesToLayoutItems } from './utils/namespaceUtils';
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '@/app/ops-analysis/components/appFullscreen';

const Topology = forwardRef<TopologyRef, TopologyProps>(
  ({ selectedTopology }, ref) => {
    const themeName = resolveOpsChartThemeName();
    const chartTheme = getOpsChartTheme(themeName);
    const isDarkTheme = themeName === 'dark';
    const containerRef = useRef<HTMLDivElement>(null);
    const canvasContainerRef = useRef<HTMLDivElement>(null);
    const canvasHostRef = useRef<HTMLDivElement>(null);
    const minimapContainerRef = useRef<HTMLDivElement>(null);
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
    const rebuildFiltersRef = useRef<(() => void) | null>(null);
    const { isFullscreen, enterFullscreen, exitFullscreen } =
      useAppViewFullscreen();
    const handleFullscreenToggle = useCallback(() => {
      if (isFullscreen) {
        exitFullscreen();
        return;
      }
      enterFullscreen();
    }, [enterFullscreen, exitFullscreen, isFullscreen]);

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
        handleSaveTopology(selectedTopology, definitions);
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
      setAppliedFilterValues,
      setAppliedNamespaceId,
      setDefinitions,
      setFilterValues,
      setNamespaceDraftId,
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

    const NodePanel =
      nodeType === 'single-value' ? SingleValueNodePanel : ShapeNodePanel;

    const panelStyle = {
      background: chartTheme.panelBg,
    };
    const topologyContainerStyle: React.CSSProperties = {
      backgroundColor: isDarkTheme ? 'var(--color-fill-1)' : '#f5f6f8',
      zIndex: isFullscreen ? 1100 : undefined,
    };

    return (
      <div
        className={`flex flex-col ${styles.topologyContainer} ${
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

            <TopologyCanvasShell
              canvasContainerRef={canvasContainerRef}
              containerRef={containerRef}
              minimapContainerRef={minimapContainerRef}
              canvasHostRef={canvasHostRef}
              isFullscreen={isFullscreen}
              loading={loading}
              minimapVisible={minimapVisible}
              panelStyle={panelStyle}
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
