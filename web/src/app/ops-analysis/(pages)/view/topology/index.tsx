import React, {
  useRef,
  useEffect,
  forwardRef,
  useImperativeHandle,
  useState,
  useCallback,
} from 'react';
import styles from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import { Spin } from 'antd';
import { AppstoreOutlined, CloseOutlined } from '@ant-design/icons';
import { v4 as uuidv4 } from 'uuid';
import { useTopologyState } from './hooks/useTopologyState';
import { useGraphOperations } from './hooks/useGraphOperations';
import { useContextMenuAndModal } from './hooks/useGraphInteractions';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
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
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import TopologyToolbar from './components/toolbar';
import ContextMenu from './components/contextMenu';
import EdgeConfigPanel from './components/edgeConfPanel';
import NodeSidebar from './components/nodeSidebar';
import NodeConfPanel from './components/nodeConfPanel';
import ViewConfig from '../dashBoard/components/viewConfig';
import ViewSelector from '../dashBoard/components/viewSelector';

const Topology = forwardRef<TopologyRef, TopologyProps>(
  ({ selectedTopology }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const canvasContainerRef = useRef<HTMLDivElement>(null);
    const minimapContainerRef = useRef<HTMLDivElement>(null);
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
    const { t } = useTranslation();
    const state = useTopologyState();
    const dataSourceManager = useDataSourceManager();

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
    } = useGraphOperations(containerRef, state, minimapContainerRef);

    const { handleEdgeConfigConfirm, closeEdgeConfig, handleMenuClick } =
      useContextMenuAndModal(containerRef, state);

    // 定时刷新处理
    const handleFrequencyChange = useCallback(
      (frequency: number) => {
        if (refreshTimerRef.current) {
          clearInterval(refreshTimerRef.current);
          refreshTimerRef.current = null;
        }

        if (frequency > 0) {
          refreshTimerRef.current = setInterval(() => {
            refreshAllSingleValueNodes();
          }, frequency);
        }
      },
      [refreshAllSingleValueNodes]
    );

    const handleRefresh = useCallback(() => {
      refreshAllSingleValueNodes();
    }, [refreshAllSingleValueNodes]);

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

    const handleTopologyViewConfigConfirm = async (
      values: ViewConfigFormValues
    ) => {
      if (!state.editingNodeData) return;
      if (state.editingNodeData.isNewNode && state.editingNodeData.position) {
        await handleAddChartNode(values);
        state.setEditingNodeData(null);
        state.setViewConfigVisible(false);
      } else {
        await handleViewConfigConfirm(values);
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
        addNewNode(nodeConfig);
      } else {
        await handleNodeUpdate(values);
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
        handleSaveTopology(selectedTopology);
      }
    };

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

      // 清除定时刷新
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }

      if (selectedTopology?.data_id && state.graphInstance) {
        handleLoadTopology(selectedTopology.data_id).finally(() => {
          setTimeout(() => {
            finishInitialization();
          }, 100);
        });
      } else if (!selectedTopology?.data_id && state.graphInstance) {
        setTimeout(() => {
          finishInitialization();
        }, 100);
      }

      return () => {
        if (refreshTimerRef.current) {
          clearInterval(refreshTimerRef.current);
          refreshTimerRef.current = null;
        }
      };
    }, [selectedTopology?.data_id, state.graphInstance]);

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
        className={`flex-1 p-4 pb-0 overflow-auto flex flex-col bg-[var(--color-bg-1)] ${styles.topologyContainer}`}
      >
        {/* 工具栏 */}
        <TopologyToolbar
          selectedTopology={selectedTopology}
          onEdit={toggleEditMode}
          onSave={handleSave}
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

        <div className="flex-1 flex overflow-hidden">
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
            className="flex-1 bg-[var(--color-bg-1)] relative"
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
          onClose={() => state.setViewConfigVisible(false)}
          onConfirm={handleTopologyViewConfigConfirm}
          dataSourceManager={dataSourceManager}
        />
      </div>
    );
  }
);

Topology.displayName = 'Topology';

export default Topology;
