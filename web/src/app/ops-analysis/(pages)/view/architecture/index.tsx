'use client';

import {
  useState,
  useEffect,
  forwardRef,
  useImperativeHandle,
  useCallback,
  useMemo,
  useRef,
} from 'react';
import styles from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import { iconList } from '@/app/cmdb/utils/common';
import { getModelIconUrl } from '@/app/cmdb/utils/modelIcon';
import { message, Spin } from 'antd';
import type {
  DiagramItemHit,
  IsoflowLabels,
  IconPickerRequest,
  IsoflowSceneApi,
  ItemControlsExtraTarget,
} from '@bk-lite/isoflow';
import { useArchitectureApi } from '@/app/ops-analysis/api/architecture';
import { useDirectoryApi } from '@/app/ops-analysis/api';
import useBtnPermissions from '@/hooks/usePermissions';
import { useCanvasPeriodicRefresh } from '@/app/ops-analysis/hooks/useCanvasPeriodicRefresh';
import {
  canPersistCanvasRefreshInterval,
  normalizeCanvasRefreshInterval,
} from '@/app/ops-analysis/utils/canvasRefreshInterval';
import { useCanvasShareAction } from '@/app/ops-analysis/hooks/useCanvasShareAction';
import { flattenCollections } from '@isoflow/isopacks/dist/utils';
import {
  DiagramData,
  ArchitectureProps,
} from '@/app/ops-analysis/types/architecture';
import dynamic from 'next/dynamic';
import isoflowIsopack from '@isoflow/isopacks/dist/isoflow';
import ArchitectureToolbar from './components/toolbar';
import IconPickerModal from './components/iconPickerModal';
import ViewWorkspace from '../components/viewWorkspace';
import { DEFAULT_COLORS } from '@/app/ops-analysis/constants/common';
import { svgToBase64 } from '@/app/ops-analysis/utils/common';
import {
  selectCmdbIsometricIcons,
  selectIsometricIsopackIcons,
} from '@/app/ops-analysis/utils/architectureIcons';
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '@/app/ops-analysis/components/appFullscreen';
import { useCanvasDraft } from '@/app/ops-analysis/hooks/useCanvasDraft';
import {
  restoreDraftRefreshInterval,
  toCanvasDraftResourceId,
  type CanvasDraftPayload,
} from '@/app/ops-analysis/api/canvasDraft';
import { bindCanvasDraftControls } from '@/app/ops-analysis/components/canvasDraftControls';
import ResourceBindingDrawer from './components/resourceBindingDrawer';
import ResourceInsertDrawer from './components/resourceInsertDrawer';
import { DisplayMetricsField, NodeBindingStrip, RegionAlertSettings } from './components/itemControlsExtra';
import ResourceDetailDrawer, {
  type ArchitectureDetailState,
} from './components/resourceDetailDrawer';
import {
  BINDING_SEARCH_PAGE_SIZE,
  bindingDisplay,
  bindingModelLabel,
  bindingSearchMode,
  findSelectionBinding,
  architectureSearchPage,
  flattenModelOptions,
  type ArchitectureBinding,
  type BindingSearchHit,
  type BindingSearchPage,
  type ModelOption,
} from './binding/model';
import {
  architectureStatusRequestMode,
  bindingStatusLoading,
  blockResourceOpen,
  STATUS_DOT_COLOR,
  buildIconPlates,
  buildNodeStatus,
  buildRectangleOverlays,
  regionAlertBadge,
  regionAlertBadgeParts,
  collectBoundUuids,
  decideDiagramClick,
  iconBindingStats,
  rectangleIconCounts,
  type OverlayLabel,
} from './binding/status';
import { useArchitectureNodeStatus } from './binding/useNodeStatus';
import {
  buildNodeMetricCards,
  collectMetricUuids,
  findNodeMetricChoice,
  type MetricChoice,
} from './binding/displayMetrics';
import { useArchitectureDisplayMetrics } from './binding/useDisplayMetrics';
import {
  architectureIconIdForModel,
  assetInsertLabel,
  insertSelection,
  planInsertTiles,
} from './binding/insertPlan';

const Isoflow = dynamic(
  () => import('@bk-lite/isoflow').then((mod) => ({ default: mod.Isoflow })),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full">
        <Spin size="large" />
      </div>
    ),
  }
);

const createArchitectureIcons = async () => {
  const cmdbIcons = await Promise.all(
    selectCmdbIsometricIcons(iconList).map(async (icon) => ({
      id: icon.id,
      name: icon.name,
      url: await svgToBase64(icon.src),
      isIsometric: true as const,
    }))
  );

  return [
    ...cmdbIcons,
    ...selectIsometricIsopackIcons(flattenCollections([isoflowIsopack])),
  ];
};

export interface ArchitectureRef {
  hasUnsavedChanges: () => boolean;
}

const Architecture = forwardRef<ArchitectureRef, ArchitectureProps>(
  ({ selectedArchitecture, shareMode = false }, ref) => {
    const { t } = useTranslation();
    const {
      getArchitectureDetail,
      saveArchitecture,
      getArchitectureModels,
      searchArchitectureResources,
    } = useArchitectureApi();
    const { updateItem } = useDirectoryApi();
    const { hasPermission } = useBtnPermissions();
    const { shareLoading, openShare } = useCanvasShareAction('architecture');
    const [diagramName, setDiagramName] = useState('');
    const [fossflowKey, setFossflowKey] = useState(0);
    const [currentModel, setCurrentModel] = useState<DiagramData | null>(null);
    const [hasUnsaved, setHasUnsaved] = useState(false);
    const [loading, setLoading] = useState(false);
    const [uniqueIcons, setUniqueIcons] = useState<any[]>([]);
    const [isEditMode, setIsEditMode] = useState(false);
    const [selection, setSelection] = useState<DiagramItemHit | null>(null);
    const [insertOpen, setInsertOpen] = useState(false);
    const [iconPicker, setIconPicker] = useState<IconPickerRequest | null>(null);
    const [insertRegionId, setInsertRegionId] = useState<string | null>(null);
    const [bindingNodeId, setBindingNodeId] = useState<string | null>(null);
    const [detail, setDetail] = useState<ArchitectureDetailState | null>(null);
    const [highlightId, setHighlightId] = useState<string | undefined>(undefined);
    const [highlightUnbound, setHighlightUnbound] = useState(false);
    const [showMetrics, setShowMetrics] = useState(true);
    const [savedRefreshInterval, setSavedRefreshInterval] = useState(0);
    const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
    const sceneApiRef = useRef<IsoflowSceneApi | null>(null);
    const searchResourcesRef = useRef(searchArchitectureResources);
    searchResourcesRef.current = searchArchitectureResources;
    /** Cross-model keyword search returns every hit; later pages are sliced locally. */
    const fulltextResultRef = useRef<{ keyword: string; raw: unknown } | null>(null);
    const [loadedArchitectureId, setLoadedArchitectureId] = useState<
      string | null
    >(null);
    const resumeEditModeAfterFullscreenRef = useRef(false);
    const { isFullscreen, enterFullscreen, exitFullscreen } =
      useAppViewFullscreen();

    const officialSnapshotRef = useRef('');
    const debounceTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const lastModelUpdateRef = useRef<string>('');
    const pendingModelSnapshotRef = useRef<string | null>(null);
    const isUpdatingRef = useRef<boolean>(false);
    const modelWriteEpochRef = useRef(0);
    const invalidatePendingModelWrite = useCallback(() => {
      modelWriteEpochRef.current += 1;
      pendingModelSnapshotRef.current = null;
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
        debounceTimeoutRef.current = null;
      }
    }, []);
    const [diagramData, setDiagramData] = useState<DiagramData>(() => {
      return {
        title: 'Untitled Diagram',
        icons: [],
        colors: DEFAULT_COLORS,
        items: [],
        views: [],
        fitToScreen: true,
      };
    });

    useEffect(() => {
      let isMounted = true;
      createArchitectureIcons().then((icons) => {
        if (isMounted) {
          setUniqueIcons(icons);
        }
      });
      return () => {
        isMounted = false;
      };
    }, []);

    useEffect(() => {
      if (uniqueIcons.length === 0) return;

      const currentArchitectureId = selectedArchitecture?.data_id;

      if (
        currentArchitectureId &&
        currentArchitectureId !== loadedArchitectureId
      ) {
        (async () => {
          try {
            setLoading(true);
            isUpdatingRef.current = true;
            invalidatePendingModelWrite();

            setCurrentModel(null);
            setSavedRefreshInterval(0);
            setDiagramData({
              title: 'Loading...',
              icons: uniqueIcons,
              colors: DEFAULT_COLORS,
              items: [],
              views: [],
              fitToScreen: true,
            });
            const data = await getArchitectureDetail(currentArchitectureId);
            const viewSets = Array.isArray(data.view_sets)
              ? { items: [], views: [] }
              : data.view_sets || { items: [], views: [] };
            if (data) {
              const mergedData: DiagramData = {
                items: viewSets.items || [],
                views: viewSets.views || [],
                title: data.name || diagramName,
                icons: uniqueIcons,
                colors: DEFAULT_COLORS,
                fitToScreen: true,
              };

              setDiagramName(data.name || '');
              setSavedRefreshInterval(normalizeCanvasRefreshInterval(data.refresh_interval));
              setDiagramData({ ...mergedData });
              setCurrentModel({ ...mergedData });
              setFossflowKey((prev) => prev + 1);
              setHasUnsaved(false);
              setLoadedArchitectureId(currentArchitectureId);
              setIsEditMode(false);

              invalidatePendingModelWrite();
              lastModelUpdateRef.current = JSON.stringify({
                items: viewSets.items || [],
                views: viewSets.views || [],
              });
            }
          } catch (error) {
            console.error('Load failed:', error);
            message.error(t('opsAnalysis.architecture.loadFailed'));
          } finally {
            setLoading(false);
            setTimeout(() => {
              isUpdatingRef.current = false;
            }, 1000);
          }
        })();
      } else if (!currentArchitectureId && loadedArchitectureId) {
        invalidatePendingModelWrite();
        setCurrentModel(null);
        setDiagramData({
          title: 'Untitled Diagram',
          icons: uniqueIcons,
          colors: DEFAULT_COLORS,
          items: [],
          views: [],
          fitToScreen: true,
        });
        setFossflowKey((prev) => prev + 1);
        setHasUnsaved(false);
        setIsEditMode(false);
        setLoadedArchitectureId(null);
        setSavedRefreshInterval(0);
        lastModelUpdateRef.current = '';
      }
    }, [
      uniqueIcons,
      selectedArchitecture?.data_id,
      loadedArchitectureId,
      invalidatePendingModelWrite,
    ]);

    const architectureDraftResourceId = toCanvasDraftResourceId(
      selectedArchitecture?.data_id,
    );
    const getArchitectureDraftPayload = useCallback(
      (): CanvasDraftPayload => {
        const pending = pendingModelSnapshotRef.current;
        const parsed = pending
          ? JSON.parse(pending) as { items?: DiagramData['items']; views?: DiagramData['views'] }
          : null;
        return {
          name: diagramName,
          view_sets: {
            items: parsed?.items || currentModel?.items || [],
            views: parsed?.views || currentModel?.views || [],
          },
          refresh_interval: savedRefreshInterval,
        };
      },
      [currentModel?.items, currentModel?.views, diagramName, savedRefreshInterval],
    );
    const applyArchitectureDraftPayload = useCallback(
      (payload: CanvasDraftPayload) => {
        invalidatePendingModelWrite();
        const viewSets = (payload.view_sets || {}) as {
          items?: DiagramData['items'];
          views?: DiagramData['views'];
        };
        isUpdatingRef.current = true;
        restoreDraftRefreshInterval(payload, setSavedRefreshInterval);
        const merged: DiagramData = {
          items: viewSets.items || [],
          views: viewSets.views || [],
          title: diagramName || 'Untitled Diagram',
          icons: uniqueIcons,
          colors: DEFAULT_COLORS,
          fitToScreen: true,
        };
        setDiagramData({ ...merged });
        setCurrentModel({ ...merged });
        setFossflowKey((prev) => prev + 1);
        setHasUnsaved(true);
        lastModelUpdateRef.current = JSON.stringify({
          items: merged.items,
          views: merged.views,
        });
        window.setTimeout(() => {
          isUpdatingRef.current = false;
        }, 0);
      },
      [diagramName, uniqueIcons, invalidatePendingModelWrite],
    );
    const architectureDraft = useCanvasDraft({
      resourceType: 'architecture',
      resourceId: architectureDraftResourceId,
      enabled: Boolean(
        isEditMode &&
          !shareMode &&
          architectureDraftResourceId &&
          !selectedArchitecture?.is_build_in,
      ),
      getPayload: getArchitectureDraftPayload,
      applyPayload: applyArchitectureDraftPayload,
    });

    const toggleEditMode = () => {
      const newEditMode = !isEditMode;
      setSelection(null);
      setIsEditMode(newEditMode);
      if (newEditMode) {
        officialSnapshotRef.current = lastModelUpdateRef.current;
        setHasUnsaved(false);
      }
    };

    const handleCancelEdit = () => {
      invalidatePendingModelWrite();
      if (officialSnapshotRef.current) {
        try {
          const parsed = JSON.parse(officialSnapshotRef.current) as {
            items?: DiagramData['items'];
            views?: DiagramData['views'];
          };
          isUpdatingRef.current = true;
          setCurrentModel((prev) =>
            prev
              ? { ...prev, items: parsed.items || [], views: parsed.views || [] }
              : prev,
          );
          setDiagramData((prev) => ({
            ...prev,
            items: parsed.items || [],
            views: parsed.views || [],
          }));
          setFossflowKey((prev) => prev + 1);
          lastModelUpdateRef.current = officialSnapshotRef.current;
          window.setTimeout(() => {
            isUpdatingRef.current = false;
          }, 0);
        } catch {
          // 进入编辑时的快照无法解析时，保持当前画面并退出编辑。
        }
      }
      setHasUnsaved(false);
      setSelection(null);
      setIsEditMode(false);
    };

    useEffect(() => {
      if (isFullscreen || !resumeEditModeAfterFullscreenRef.current) {
        return;
      }

      resumeEditModeAfterFullscreenRef.current = false;
      setIsEditMode(true);
    }, [isFullscreen]);

    const handleFullscreenToggle = useCallback(() => {
      if (isFullscreen) {
        exitFullscreen();
        return;
      }

      resumeEditModeAfterFullscreenRef.current = isEditMode;
      if (isEditMode) {
        setIsEditMode(false);
      }
      enterFullscreen();
    }, [enterFullscreen, exitFullscreen, isEditMode, isFullscreen]);

    const saveDiagram = async () => {
      if (!selectedArchitecture?.data_id || !currentModel) {
        return;
      }
      const pending = pendingModelSnapshotRef.current;
      const persisted = pending
        ? JSON.parse(pending) as { items?: DiagramData['items']; views?: DiagramData['views'] }
        : { items: currentModel.items, views: currentModel.views };
      const items = persisted.items || [];
      const views = persisted.views || [];
      if (pending) {
        invalidatePendingModelWrite();
        setCurrentModel((prev) => (prev ? { ...prev, items, views } : prev));
      }
      try {
        setLoading(true);

        const saveData = {
          name: diagramName,
          view_sets: {
            views,
            items,
          },
        };

        await saveArchitecture(selectedArchitecture.data_id, saveData);

        lastModelUpdateRef.current = JSON.stringify({
          items,
          views,
        });

        setHasUnsaved(false);
        setIsEditMode(false);
        message.success(t('topology.architecture.diagramSaved'));
      } catch {
        if (pending) setHasUnsaved(true);
        message.error(t('topology.architecture.saveFailed'));
      } finally {
        setLoading(false);
      }
    };

    const handleModelUpdated = useCallback(
      (model: DiagramData) => {
        if (isUpdatingRef.current) {
          return;
        }

        if (!selectedArchitecture?.data_id) {
          return;
        }

        try {
          const modelSnapshot = JSON.stringify({
            items: model.items || [],
            views: model.views || [],
          });

          if (modelSnapshot === lastModelUpdateRef.current) {
            return;
          }

          pendingModelSnapshotRef.current = modelSnapshot;
          if (debounceTimeoutRef.current) {
            clearTimeout(debounceTimeoutRef.current);
          }

          const epoch = modelWriteEpochRef.current;
          debounceTimeoutRef.current = setTimeout(() => {
            if (epoch !== modelWriteEpochRef.current) return;

            try {
              const newModelData = {
                items: JSON.parse(JSON.stringify(model.items)) || [],
                views: JSON.parse(JSON.stringify(model.views)) || [],
              };

              setCurrentModel((prevModel) => {
                if (!prevModel) return null;
                return {
                  ...prevModel,
                  items: newModelData.items,
                  views: newModelData.views,
                };
              });
              if (isEditMode) {
                setHasUnsaved(true);
              }
              lastModelUpdateRef.current = modelSnapshot;
              pendingModelSnapshotRef.current = null;
            } catch (error) {
              console.error('Error updating model state:', error);
            }
          }, 300);
        } catch (error) {
          console.error('Error in handleModelUpdated:', error);
        }
      },
      [selectedArchitecture?.data_id, isEditMode]
    );

    const bindingEditable = isEditMode && !shareMode;
    const bindingDrawerOpen = Boolean(
      bindingEditable
      && bindingNodeId
      && selection?.type === 'ITEM'
      && selection.id === bindingNodeId,
    );
    const drawerBinding = useMemo(
      () => (bindingNodeId
        ? findSelectionBinding(currentModel?.views, { type: 'ITEM', id: bindingNodeId })
        : null),
      [bindingNodeId, currentModel?.views],
    );

    // The drawer belongs to one icon. Selecting another item or clearing the selection closes it.
    useEffect(() => {
      if (!bindingNodeId) return;
      if (!bindingEditable || selection?.type !== 'ITEM' || selection.id !== bindingNodeId) {
        setBindingNodeId(null);
      }
    }, [bindingEditable, bindingNodeId, selection]);

    useEffect(() => {
      if (shareMode) return undefined;
      let cancelled = false;
      getArchitectureModels()
        .then((data) => {
          if (!cancelled) setModelOptions(flattenModelOptions(data));
        })
        .catch(() => {
          if (!cancelled) setModelOptions([]);
        });
      return () => {
        cancelled = true;
      };
    }, [getArchitectureModels, shareMode]);

    const diagramViews = currentModel?.views ?? diagramData.views;
    const boundUuids = useMemo(() => collectBoundUuids(diagramViews), [diagramViews]);
    const placedUuids = useMemo(() => new Set(boundUuids), [boundUuids]);
    const requestMode = architectureStatusRequestMode({
      shareMode,
      editMode: isEditMode,
    });
    const modelNames = useMemo(
      () => Object.fromEntries(modelOptions.map((model) => [model.model_id, model.model_name])),
      [modelOptions],
    );
    const iconNames = useMemo(() => {
      const source = currentModel?.items ?? diagramData.items;
      const names: Record<string, string> = {};
      if (!Array.isArray(source)) return names;
      for (const item of source) {
        if (!item || typeof item !== 'object') continue;
        const id = (item as { id?: unknown }).id;
        const name = (item as { name?: unknown }).name;
        if (typeof id === 'string') names[id] = typeof name === 'string' ? name : '';
      }
      return names;
    }, [currentModel?.items, diagramData.items]);
    const viewStatus = useArchitectureNodeStatus({
      enabled: requestMode === 'poll',
      uuids: boundUuids,
      intervalMs: 0,
      refreshOnVisible: false,
    });
    const editStatus = useArchitectureNodeStatus({
      enabled: requestMode === 'once',
      uuids: boundUuids,
      intervalMs: 0,
    });
    const metricUuids = useMemo(() => collectMetricUuids(diagramViews), [diagramViews]);
    const selectedBoundUuid = useMemo(() => {
      if (!isEditMode || shareMode || selection?.type !== 'ITEM') return '';
      return findSelectionBinding(diagramViews, selection)?.binding?.inst_uuid ?? '';
    }, [diagramViews, isEditMode, selection, shareMode]);
    const viewMetrics = useArchitectureDisplayMetrics({
      enabled: !shareMode && !isEditMode,
      uuids: metricUuids,
      intervalMs: 0,
      refreshOnVisible: false,
    });
    const editMetrics = useArchitectureDisplayMetrics({
      enabled: !shareMode && isEditMode && Boolean(selectedBoundUuid),
      uuids: selectedBoundUuid ? [selectedBoundUuid] : [],
      intervalMs: 0,
    });
    const refreshArchitectureLive = useCallback(() => {
      viewStatus.reload();
      viewMetrics.reload();
    }, [viewMetrics.reload, viewStatus.reload]);
    const canPersistRefreshInterval = canPersistCanvasRefreshInterval({
      shareMode,
      isBuiltIn: Boolean(selectedArchitecture?.is_build_in),
      hasEditPermission: hasPermission(['EditChart']),
    });
    const { effectiveRefreshInterval, handleFrequencyChange } =
      useCanvasPeriodicRefresh({
        canvasId: selectedArchitecture?.data_id,
        savedInterval: savedRefreshInterval,
        canPersist: canPersistRefreshInterval,
        enabled: !shareMode && !isEditMode,
        patchRefreshInterval: async (interval) => {
          if (!selectedArchitecture?.data_id) {
            return;
          }
          await updateItem('architecture', selectedArchitecture.data_id, {
            refresh_interval: interval,
          });
        },
        onPeriodicRefresh: () => {
          refreshArchitectureLive();
        },
        onSavedIntervalChange: setSavedRefreshInterval,
      });
    const statusByUuid = requestMode === 'poll' ? viewStatus.byUuid : editStatus.byUuid;
    const drawerStatus = drawerBinding?.binding
      ? editStatus.byUuid[drawerBinding.binding.inst_uuid] ?? null
      : null;

    useEffect(() => {
      setDetail(null);
      setHighlightId(undefined);
      setHighlightUnbound(false);
    }, [loadedArchitectureId, isEditMode, shareMode]);

    const searchResources = useCallback(
      async (
        keyword: string,
        modelId: string,
        page: number,
        pageSize = BINDING_SEARCH_PAGE_SIZE,
      ): Promise<BindingSearchPage> => {
        const mode = bindingSearchMode(keyword, modelId);
        if (mode === 'idle') {
          return { hits: [], hasMore: false, total: 0 };
        }
        const text = keyword.trim();
        const model = modelId.trim();
        if (mode === 'fulltext') {
          const cached = fulltextResultRef.current;
          if (page === 1 || !cached || cached.keyword !== text) {
            fulltextResultRef.current = {
              keyword: text,
              raw: await searchResourcesRef.current({
                keyword: text,
                model_id: '',
                page,
                page_size: pageSize,
                case_sensitive: false,
              }),
            };
          }
          return architectureSearchPage(fulltextResultRef.current?.raw, page, pageSize);
        }
        const raw = await searchResourcesRef.current({
          keyword: text,
          model_id: model,
          page,
          page_size: pageSize,
          case_sensitive: false,
        });
        return architectureSearchPage(raw, page, pageSize);
      },
      [],
    );

    const openInsert = useCallback(() => {
      setInsertRegionId(selection?.type === 'RECTANGLE' ? selection.id : null);
      setInsertOpen(true);
    }, [selection]);

    const confirmInsert = useCallback((hits: BindingSearchHit[]) => {
      const api = sceneApiRef.current;
      const ready = insertSelection(hits, placedUuids);
      if (!api) {
        message.error(t('opsAnalysis.architecture.insertFailed'));
        return;
      }
      if (ready.length === 0) {
        setInsertOpen(false);
        return;
      }
      const placement = api.readPlacement();
      const region = insertRegionId
        ? placement.rectangles.find((item) => item.id === insertRegionId)
        : null;
      if (insertRegionId && !region) {
        message.error(t('opsAnalysis.architecture.insertFailed'));
        return;
      }
      const tiles = planInsertTiles({
        count: ready.length,
        occupied: placement.occupied,
        region: region ?? null,
        origin: placement.viewportCenter,
      });
      if (tiles.length !== ready.length) {
        message.error(t('opsAnalysis.architecture.insertFailed'));
        return;
      }
      try {
        const nodes = ready.map((hit, index) => {
          const model = modelOptions.find((item) => item.model_id === hit.model_id);
          return {
            id: crypto.randomUUID(),
            name: assetInsertLabel(hit, t('opsAnalysis.architecture.unnamedIcon')),
            icon: architectureIconIdForModel(
              model?.icn,
              getModelIconUrl({
                icn: model?.icn || '',
                model_id: hit.model_id,
              }),
              placement.iconIds,
            ),
            tile: tiles[index],
            bkBinding: { inst_uuid: hit.inst_uuid, model_id: hit.model_id },
          };
        });
        if (nodes.some((node) => !placement.iconIds.includes(node.icon))) {
          message.error(t('opsAnalysis.architecture.insertFailed'));
          return;
        }
        api.createBoundNodes(nodes);
        api.revealTiles(tiles);
        setInsertOpen(false);
        message.success(t('opsAnalysis.architecture.insertDone'));
      } catch {
        message.error(t('opsAnalysis.architecture.insertFailed'));
      }
    }, [insertRegionId, modelOptions, placedUuids, t]);

    const updateNodeBinding = useCallback(
      (id: string, bkBinding: ArchitectureBinding | undefined) => {
        sceneApiRef.current?.updateViewItem(id, {
          bkBinding,
          bkDisplayMetrics: undefined,
        });
      },
      [],
    );

    const updateNodeMetrics = useCallback((id: string, bkDisplayMetrics: MetricChoice | undefined) => {
      sceneApiRef.current?.updateViewItem(id, { bkDisplayMetrics });
    }, []);

    const handleItemSelect = useCallback((item: DiagramItemHit | null) => {
      if (!item || (item.type !== 'ITEM' && item.type !== 'RECTANGLE')) {
        setSelection(null);
        return;
      }
      setSelection(item);
    }, []);

    const alertLevelLabel = useCallback((level: string) => {
      const key: Record<string, string> = {
        critical: 'opsAnalysis.architecture.levelCritical',
        error: 'opsAnalysis.architecture.levelError',
        warning: 'opsAnalysis.architecture.levelWarning',
      };
      const messageKey = key[level.trim().toLowerCase()];
      return messageKey ? t(messageKey) : level;
    }, [t]);

    const statusHintText = useCallback((hint: 'unmonitored' | 'unknown' | 'forbidden' | 'invalid') => {
      if (hint === 'unmonitored') return t('opsAnalysis.architecture.hintUnmonitored');
      if (hint === 'forbidden') return t('opsAnalysis.architecture.hintForbidden');
      if (hint === 'invalid') return t('opsAnalysis.architecture.hintInvalid');
      return t('opsAnalysis.architecture.hintUnknown');
    }, [t]);

    const overlayText = useCallback((label: OverlayLabel | undefined) => {
      if (!label || label.type === 'pending' || label.type === 'empty') return undefined;
      if (label.type === 'text') return label.value;
      if (label.type === 'invalid') return t('opsAnalysis.architecture.bindingInvalid');
      if (label.type === 'forbidden') return t('opsAnalysis.architecture.bindingForbidden');
      return t('opsAnalysis.architecture.bindingUnknown');
    }, [t]);

    const nodeStatus = useMemo(() => {
      if (requestMode === 'off') return undefined;
      if (requestMode === 'once') {
        const source = Object.keys(editStatus.byUuid).length
          ? editStatus.byUuid
          : viewStatus.byUuid;
        if (!Object.keys(source).length) return undefined;
        const plates = buildIconPlates(diagramViews, source, modelNames, iconNames, {
          nameAndType: true,
        });
        const next: Record<string, {
          plateTitle?: string;
          plateSubtitle?: string;
          hoverName?: string;
          hoverModel?: string;
        }> = {};
        for (const [id, plate] of Object.entries(plates)) {
          const entry: {
            plateTitle?: string;
            plateSubtitle?: string;
            hoverName?: string;
            hoverModel?: string;
          } = {};
          if (plate.title) entry.plateTitle = plate.title;
          if (plate.line === 'forbidden') entry.plateSubtitle = t('opsAnalysis.architecture.bindingForbidden');
          else if (plate.line === 'invalid') entry.plateSubtitle = t('opsAnalysis.architecture.plateInvalid');
          else if (plate.subtitle) entry.plateSubtitle = plate.subtitle;
          if (plate.hoverName) entry.hoverName = plate.hoverName;
          if (plate.hoverModel) entry.hoverModel = plate.hoverModel;
          if (entry.plateTitle || entry.plateSubtitle || entry.hoverName) next[id] = entry;
        }
        return Object.keys(next).length ? next : undefined;
      }
      if (viewStatus.phase === 'idle' && Object.keys(viewStatus.byUuid).length === 0) {
        return undefined;
      }
      const overlays = buildNodeStatus(diagramViews, viewStatus.byUuid);
      const plates = buildIconPlates(diagramViews, viewStatus.byUuid, modelNames, iconNames);
      const next: Record<string, {
        level: 'normal' | 'warning' | 'critical' | 'unmonitored' | 'unknown' | 'invalid' | 'forbidden';
        count?: number;
        hint?: string;
        badgeHint?: string;
        plateMark?: string;
        plateTitle?: string;
        plateSubtitle?: string;
        hoverName?: string;
        hoverModel?: string;
        hoverModelLabel?: string;
        hoverStatusLabel?: string;
        hoverAlert?: string;
      }> = {};
      for (const [id, overlay] of Object.entries(overlays)) {
        const entry: {
          level: typeof overlay.level;
          count?: number;
          hint?: string;
          badgeHint?: string;
          plateMark?: string;
          plateTitle?: string;
          plateSubtitle?: string;
          hoverName?: string;
          hoverModel?: string;
          hoverModelLabel?: string;
          hoverStatusLabel?: string;
          hoverAlert?: string;
        } = {
          level: overlay.level,
        };
        if (typeof overlay.count === 'number') entry.count = overlay.count;
        if (overlay.hint) entry.hint = statusHintText(overlay.hint);
        if (overlay.level === 'normal') {
          entry.hint = t('opsAnalysis.architecture.statusNormal');
          entry.hoverStatusLabel = t('opsAnalysis.architecture.alertLabel');
        }
        if (overlay.badgeName && typeof overlay.count === 'number') {
          entry.badgeHint = t('opsAnalysis.architecture.alertBadgeHint', undefined, {
            name: overlay.badgeName,
            count: overlay.count,
            level: alertLevelLabel(overlay.badgeLevel || overlay.level),
          });
          entry.plateMark = String(overlay.count);
          entry.hoverAlert = t('opsAnalysis.architecture.hoverAlert', undefined, {
            count: overlay.count,
            level: alertLevelLabel(overlay.badgeLevel || overlay.level),
          });
          entry.hoverStatusLabel = t('opsAnalysis.architecture.alertLabel');
        } else if (overlay.level === 'forbidden') {
          entry.plateMark = t('opsAnalysis.architecture.bindingForbidden');
        } else if (overlay.level === 'invalid') {
          entry.plateMark = t('opsAnalysis.architecture.bindingInvalid');
        }
        const plate = plates[id];
        if (plate?.title) entry.plateTitle = plate.title;
        if (plate?.subtitle) entry.plateSubtitle = plate.subtitle;
        if (plate) {
          if (plate.hoverName) entry.hoverName = plate.hoverName;
          if (plate.hoverModel) {
            entry.hoverModel = plate.hoverModel;
            entry.hoverModelLabel = t('opsAnalysis.architecture.modelLabel');
          }
        }
        next[id] = entry;
      }
      return Object.keys(next).length ? next : undefined;
    }, [
      alertLevelLabel,
      diagramViews,
      editStatus.byUuid,
      iconNames,
      modelNames,
      requestMode,
      statusHintText,
      t,
      viewStatus.byUuid,
      viewStatus.phase,
    ]);

    const rectangleStatus = useMemo(() => {
      if (requestMode === 'off') return undefined;
      const viewing = requestMode === 'poll';
      const source = viewing ? viewStatus.byUuid : editStatus.byUuid;
      if (viewing && viewStatus.phase === 'idle' && Object.keys(source).length === 0) {
        return undefined;
      }
      const overlays = buildRectangleOverlays(diagramViews, source, {
        followBorders: viewing,
      });
      const next: Record<string, {
        label?: string;
        badgeLevel?: 'critical' | 'warning';
        badgeCount?: number;
        badgeHint?: string;
      }> = {};
      for (const [id, overlay] of Object.entries(overlays)) {
        const label = overlayText(overlay.label);
        const entry: {
          label?: string;
          badgeLevel?: 'critical' | 'warning';
          badgeCount?: number;
          badgeHint?: string;
        } = {};
        if (label) entry.label = label;
        const parts = regionAlertBadgeParts(overlay, {
          critical: t('opsAnalysis.architecture.levelCritical'),
          warning: t('opsAnalysis.architecture.levelWarning'),
        });
        const badge = regionAlertBadge(overlay);
        if (viewing && badge) {
          // Deduped total, coloured by the highest level; the hover text keeps the per-level split.
          entry.badgeLevel = badge.level;
          entry.badgeCount = badge.count;
          entry.badgeHint = [
            parts.map((part) => part.text).join(' · '),
            t('opsAnalysis.architecture.resourceAlertHint', undefined, {
              n: overlay.resourceCount ?? 0,
              m: badge.count,
            }),
          ].join('\n');
        }
        if (entry.label || entry.badgeLevel) next[id] = entry;
      }
      return Object.keys(next).length ? next : undefined;
    }, [
      diagramViews,
      editStatus.byUuid,
      overlayText,
      requestMode,
      t,
      viewStatus.byUuid,
      viewStatus.phase,
    ]);

    const nodeMetrics = useMemo(() => {
      if (shareMode || isEditMode) return undefined;
      const cards = buildNodeMetricCards(diagramViews, viewMetrics.byUuid, viewMetrics.objects);
      const next: Record<string, { lines: { name: string; text: string }[]; pinned: boolean }> = {};
      for (const [id, card] of Object.entries(cards)) {
        next[id] = { lines: card.lines, pinned: showMetrics };
      }
      return Object.keys(next).length ? next : undefined;
    }, [diagramViews, isEditMode, shareMode, showMetrics, viewMetrics.byUuid, viewMetrics.objects]);

    const bindingStats = useMemo(() => iconBindingStats(diagramViews), [diagramViews]);

    const renderItemControlsExtra = useCallback((item: ItemControlsExtraTarget) => {
      const found = findSelectionBinding(diagramViews, item);
      if (!found) return null;
      if (item.type === 'RECTANGLE') {
        const counts = rectangleIconCounts(diagramViews, item.id);
        return (
          <RegionAlertSettings
            followAlert={found.followAlert}
            iconTotal={counts.total}
            iconBound={counts.bound}
            onFollowAlert={(enabled) => {
              sceneApiRef.current?.updateRectangle(item.id, { bkFollowAlert: enabled });
            }}
          />
        );
      }
      const binding = found.binding;
      const status = binding ? editStatus.byUuid[binding.inst_uuid] ?? null : null;
      const display = bindingDisplay(status, bindingModelLabel(modelOptions, status?.model_id ?? ''));
      const name = display.blocked === 'invalid'
        ? t('opsAnalysis.architecture.bindingInvalid')
        : display.blocked === 'forbidden'
          ? t('opsAnalysis.architecture.bindingForbidden')
          : display.blocked
            ? t('opsAnalysis.architecture.bindingUnknown')
            : display.name;
      const metricItem = binding ? editMetrics.byUuid[binding.inst_uuid] : undefined;
      const metricColumns = metricItem
        ? editMetrics.objects[metricItem.monitor_object_id]?.columns ?? []
        : [];
      return (
        <div className="flex w-full min-w-0 flex-col gap-6">
          <NodeBindingStrip
            bound={Boolean(binding)}
            loading={bindingStatusLoading(Boolean(binding), status, editStatus.phase)}
            name={name}
            model={display.blocked ? '' : display.typeName}
            dotColor={STATUS_DOT_COLOR[status?.status ?? 'unknown']}
            onOpen={() => setBindingNodeId(item.id)}
            onUnbind={() => updateNodeBinding(item.id, undefined)}
          />
          {binding ? (
            <DisplayMetricsField
              columns={metricColumns}
              choice={findNodeMetricChoice(diagramViews, item.id)}
              loading={editMetrics.phase === 'idle'}
              failed={editMetrics.phase === 'failed' && !metricItem}
              onRetry={editMetrics.reload}
              onChange={(next) => updateNodeMetrics(item.id, next)}
            />
          ) : null}
        </div>
      );
    }, [
      diagramViews,
      editMetrics.byUuid,
      editMetrics.objects,
      editMetrics.phase,
      editMetrics.reload,
      editStatus.byUuid,
      editStatus.phase,
      modelOptions,
      t,
      updateNodeBinding,
      updateNodeMetrics,
    ]);

    const editorLabels = useMemo<IsoflowLabels>(() => ({
      icon: t('opsAnalysis.architecture.editor.icon'),
      replaceIcon: t('opsAnalysis.architecture.editor.replaceIcon'),
      updateIcon: t('opsAnalysis.architecture.editor.updateIcon'),
      nodeSettings: t('opsAnalysis.architecture.editor.nodeSettings'),
      settings: t('opsAnalysis.architecture.editor.settings'),
      name: t('opsAnalysis.architecture.editor.name'),
      description: t('opsAnalysis.architecture.editor.description'),
      labelHeight: t('opsAnalysis.architecture.editor.labelHeight'),
      descriptionPlaceholder: t('opsAnalysis.architecture.editor.descriptionPlaceholder'),
      delete: t('opsAnalysis.architecture.editor.delete'),
      untitledNode: t('opsAnalysis.architecture.unnamedIcon'),
      width: t('opsAnalysis.architecture.editor.width'),
      style: t('opsAnalysis.architecture.editor.style'),
      styleSolid: t('opsAnalysis.architecture.editor.styleSolid'),
      styleDotted: t('opsAnalysis.architecture.editor.styleDotted'),
      styleDashed: t('opsAnalysis.architecture.editor.styleDashed'),
      textSize: t('opsAnalysis.architecture.editor.textSize'),
      alignment: t('opsAnalysis.architecture.editor.alignment'),
      newText: t('opsAnalysis.architecture.editor.newText'),
      searchIcons: t('opsAnalysis.architecture.editor.searchIcons'),
      dragHint: t('opsAnalysis.architecture.editor.dragHint'),
      toolSelect: t('opsAnalysis.architecture.editor.toolSelect'),
      toolPan: t('opsAnalysis.architecture.editor.toolPan'),
      toolAddItem: t('opsAnalysis.architecture.editor.toolAddItem'),
      toolRectangle: t('opsAnalysis.architecture.editor.toolRectangle'),
      toolConnector: t('opsAnalysis.architecture.editor.toolConnector'),
      toolText: t('opsAnalysis.architecture.editor.toolText'),
      toolCollapse: t('opsAnalysis.architecture.editor.toolCollapse'),
      toolExpand: t('opsAnalysis.architecture.editor.toolExpand'),
      zoomIn: t('opsAnalysis.architecture.editor.zoomIn'),
      zoomOut: t('opsAnalysis.architecture.editor.zoomOut'),
      fitToScreen: t('opsAnalysis.architecture.editor.fitToScreen'),
      sendBackward: t('opsAnalysis.architecture.editor.sendBackward'),
      bringForward: t('opsAnalysis.architecture.editor.bringForward'),
      sendToBack: t('opsAnalysis.architecture.editor.sendToBack'),
      bringToFront: t('opsAnalysis.architecture.editor.bringToFront'),
      mainMenu: t('opsAnalysis.architecture.editor.mainMenu'),
      open: t('opsAnalysis.architecture.editor.open'),
      exportJson: t('opsAnalysis.architecture.editor.exportJson'),
      exportImage: t('opsAnalysis.architecture.editor.exportImage'),
      clearCanvas: t('opsAnalysis.architecture.editor.clearCanvas'),
      exportBrowserWarning: t('opsAnalysis.architecture.editor.exportBrowserWarning'),
      exportBrowserAdvice: t('opsAnalysis.architecture.editor.exportBrowserAdvice'),
      exportOptions: t('opsAnalysis.architecture.editor.exportOptions'),
      showGrid: t('opsAnalysis.architecture.editor.showGrid'),
      backgroundColor: t('opsAnalysis.architecture.editor.backgroundColor'),
      cancel: t('common.cancel'),
      downloadPng: t('opsAnalysis.architecture.editor.downloadPng'),
      exportFailed: t('opsAnalysis.architecture.editor.exportFailed'),
      exportPreview: t('opsAnalysis.architecture.editor.exportPreview'),
    }), [t]);

    const nodeBinding = useMemo(() => {
      if (requestMode !== 'once' || !highlightUnbound) return undefined;
      const marks: Record<string, { unbound: true }> = {};
      for (const id of bindingStats.unboundIds) marks[id] = { unbound: true };
      return Object.keys(marks).length ? marks : undefined;
    }, [bindingStats, highlightUnbound, requestMode]);

    const closeDetail = useCallback(() => {
      setDetail(null);
      setHighlightId(undefined);
    }, []);

    const handleItemClick = useCallback((item: DiagramItemHit | null) => {
      const action = decideDiagramClick({
        hit: item,
        views: diagramViews,
        statusByUuid: viewStatus.byUuid,
      });
      if (action.type === 'toast') {
        const key = action.reason === 'unbound'
          ? 'opsAnalysis.architecture.unboundNode'
          : action.reason === 'forbidden'
            ? 'opsAnalysis.architecture.bindingForbidden'
            : 'opsAnalysis.architecture.bindingInvalid';
        message.warning(t(key));
        closeDetail();
        return;
      }
      if (action.type === 'close') {
        closeDetail();
        return;
      }
      if (action.type === 'resource') {
        setHighlightId(action.highlightId);
        setDetail({
          kind: 'resource',
          instUuid: action.instUuid,
          modelId: action.modelId,
          highlightId: action.highlightId,
        });
        return;
      }
      setHighlightId(undefined);
      if (action.type === 'region') {
        setDetail({ kind: 'region', rectangleId: action.rectangleId });
        return;
      }
      setDetail({ kind: 'connector', connectorId: action.connectorId });
    }, [closeDetail, diagramViews, t, viewStatus.byUuid]);

    const openResource = useCallback((target: {
      instUuid: string;
      modelId: string;
      highlightId?: string;
    }) => {
      const blocked = blockResourceOpen(statusByUuid[target.instUuid]);
      if (blocked) return;
      setHighlightId(target.highlightId);
      setDetail((current) => ({
        kind: 'resource',
        instUuid: target.instUuid,
        modelId: target.modelId,
        highlightId: target.highlightId,
        returnTo: current && current.kind !== 'resource' ? current : undefined,
      }));
    }, [statusByUuid]);

    const backDetail = useCallback(() => {
      setHighlightId(undefined);
      setDetail((current) => (
        current && current.kind === 'resource' ? current.returnTo ?? null : null
      ));
    }, []);

    const hasUnsavedChanges = () => {
      return isEditMode && hasUnsaved;
    };

    useImperativeHandle(ref, () => ({
      hasUnsavedChanges,
    }));

    useEffect(() => {
      return () => {
        if (debounceTimeoutRef.current) {
          clearTimeout(debounceTimeoutRef.current);
        }
      };
    }, []);

    const architectureToolbar = (
      <ArchitectureToolbar
        selectedArchitecture={selectedArchitecture}
        isEditMode={isEditMode}
        isFullscreen={isFullscreen}
        shareMode={shareMode}
        shareLoading={shareLoading}
        onOpenShare={
          !shareMode && selectedArchitecture?.data_id
            ? () => {
              void openShare(selectedArchitecture.data_id);
            }
            : undefined
        }
        loading={loading}
        onEdit={toggleEditMode}
        onCancel={handleCancelEdit}
        onSave={saveDiagram}
        editExtra={bindCanvasDraftControls(architectureDraft)}
        onFullscreenToggle={handleFullscreenToggle}
        onAddResources={bindingEditable ? openInsert : undefined}
        showMetrics={showMetrics}
        onShowMetricsChange={setShowMetrics}
        onRefresh={shareMode || isEditMode ? undefined : refreshArchitectureLive}
        onFrequencyChange={shareMode || isEditMode ? undefined : handleFrequencyChange}
        frequenceValue={effectiveRefreshInterval}
        bindingMeter={isEditMode ? {
          bound: bindingStats.bound,
          total: bindingStats.total,
          unbound: bindingStats.unboundIds.length,
          highlightUnbound,
          onToggleHighlight: () => setHighlightUnbound((current) => !current),
        } : undefined}
      />
    );

    return (
      <div
        className={`flex flex-col ${
          isFullscreen
            ? 'fixed inset-0 h-screen w-screen overflow-hidden'
            : 'h-full min-h-0 flex-1 overflow-hidden'
        }`}
        style={{
          backgroundColor: 'var(--color-fill-1)',
          zIndex: isFullscreen ? 1100 : undefined,
        }}
      >
        <AppViewFullscreenExit visible={isFullscreen} onExit={exitFullscreen} />
        <ViewWorkspace
          selectedItem={selectedArchitecture}
          loading={loading}
          titleFallback={t('opsAnalysis.architecture.canvasTitle')}
          emptyDescription={t('opsAnalysis.architecture.emptySelect')}
          headerVisible={!isFullscreen}
          flushContent
          contentClassName="bg-[var(--color-fill-1)]"
          toolbar={isFullscreen ? undefined : architectureToolbar}
        >
        <div
          className={`relative h-full min-h-0 architecture-canvas ${styles.architectureCanvas}`}
        >
          <Isoflow
            key={`${fossflowKey}-edit`}
            initialData={diagramData}
            onModelUpdated={handleModelUpdated}
            editorMode={shareMode || !isEditMode ? 'EXPLORABLE_READONLY' : 'EDITABLE'}
            sceneApiRef={sceneApiRef}
            onItemSelect={isEditMode && !shareMode ? handleItemSelect : undefined}
            onItemClick={requestMode === 'poll' ? handleItemClick : undefined}
            highlightedItemId={requestMode === 'poll' ? highlightId : undefined}
            nodeStatus={nodeStatus}
            nodeMetrics={nodeMetrics}
            nodeBinding={nodeBinding}
            rectangleStatus={rectangleStatus}
            renderItemControlsExtra={bindingEditable ? renderItemControlsExtra : undefined}
            labels={editorLabels}
            onOpenIconPicker={setIconPicker}
          />
          <IconPickerModal request={iconPicker} onClose={() => setIconPicker(null)} />
          {shareMode ? (
            <div
              data-testid="architecture-share-hint"
              className="pointer-events-none absolute right-3 top-3 z-20 rounded bg-[var(--color-fill-2)] px-2 py-1 text-xs text-[var(--color-text-3)]"
            >
              {t('opsAnalysis.architecture.shareStatusHint')}
            </div>
          ) : null}
          {bindingEditable ? (
            <ResourceInsertDrawer
              open={insertOpen}
              models={modelOptions}
              placedUuids={placedUuids}
              onSearch={searchResources}
              onConfirm={confirmInsert}
              onClose={() => setInsertOpen(false)}
            />
          ) : null}
          {bindingEditable ? (
            <ResourceBindingDrawer
              open={bindingDrawerOpen}
              binding={drawerBinding?.binding ?? null}
              status={drawerStatus}
              statusPhase={editStatus.phase}
              iconName={bindingNodeId ? iconNames[bindingNodeId] ?? '' : ''}
              modelName={bindingModelLabel(modelOptions, drawerStatus?.model_id ?? '')}
              models={modelOptions}
              onSearch={searchResources}
              onBind={(hit) => {
                if (!bindingNodeId) return;
                updateNodeBinding(bindingNodeId, { inst_uuid: hit.inst_uuid, model_id: hit.model_id });
                setBindingNodeId(null);
                message.success(t('opsAnalysis.architecture.bindingBound', undefined, {
                  name: hit.inst_name || hit.inst_uuid,
                }));
              }}
              onUnbind={() => {
                if (bindingNodeId) updateNodeBinding(bindingNodeId, undefined);
              }}
              onClose={() => setBindingNodeId(null)}
            />
          ) : null}
          {requestMode === 'poll' && detail ? (
            <ResourceDetailDrawer
              detail={detail}
              views={diagramViews}
              items={currentModel?.items ?? diagramData.items}
              statusByUuid={viewStatus.byUuid}
              modelNames={modelNames}
              onClose={closeDetail}
              onBack={backDetail}
              onOpenResource={openResource}
            />
          ) : null}
        </div>
        </ViewWorkspace>
      </div>
    );
  }
);

Architecture.displayName = 'Architecture';

export default Architecture;
