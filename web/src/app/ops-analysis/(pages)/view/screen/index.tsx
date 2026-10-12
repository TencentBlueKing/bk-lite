"use client";

import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type SetStateAction,
} from "react";
import { message, Modal, Select, Tabs } from "antd";
import { useTranslation } from "@/utils/i18n";
import { useScreenApi } from "@/app/ops-analysis/api/screen";
import { useDirectoryApi } from "@/app/ops-analysis/api";
import useBtnPermissions from "@/hooks/usePermissions";
import { useCanvasPeriodicRefresh } from "@/app/ops-analysis/hooks/useCanvasPeriodicRefresh";
import { canPersistCanvasRefreshInterval, normalizeCanvasRefreshInterval } from "@/app/ops-analysis/utils/canvasRefreshInterval";
import type { CanvasRuntimeRefreshCause } from "@/app/ops-analysis/utils/canvasRefreshTimer";
import { useCanvasShareAction } from "@/app/ops-analysis/hooks/useCanvasShareAction";
import {
  UnifiedFilterBar,
  UnifiedFilterConfigModal,
} from "@/app/ops-analysis/components/unifiedFilter";
import { useOpsAnalysis } from "@/app/ops-analysis/context/common";
import { useShareOrganizationSeed } from "@/app/ops-analysis/context/shareOrganization";
import { useCanvasResources } from "@/app/ops-analysis/hooks/useCanvasResources";
import { useDataSourceManager } from "@/app/ops-analysis/hooks/useDataSource";
import { areScreenDataConfigPropsEqual } from "./utils/screenDataConfigProps";
import { useOpsAnalysisQueryState } from "@/app/ops-analysis/hooks/useOpsAnalysisQueryState";
import {
  collectScreenDataSourceIds,
  collectScreenNamespaceIds,
} from "@/app/ops-analysis/utils/canvasResources";
import type {
  ComponentSelectorConfigItem,
  FilterValue,
  LayoutItem,
  UnifiedFilterDefinition,
  WidgetConfig,
} from "@/app/ops-analysis/types/dashBoard";
import type {
  ScreenDecorationPresetId,
  ScreenDecorationType,
  ScreenItem,
  ScreenProps,
  ScreenShapeKind,
  ScreenTitleFramePresetId,
  ScreenViewSets,
  ScreenViewportConfig,
  ScreenWidgetItem,
} from "@/app/ops-analysis/types/screen";
import {
  useAppViewFullscreen,
} from "@/app/ops-analysis/components/appFullscreen";
import ViewWorkspace from "../components/viewWorkspace";
import ScreenCanvas from "./components/screenCanvas";
import {
  ScreenItemContextMenu,
  buildScreenItemMenu,
  type ScreenItemMenuKey,
} from "./components/screenItemMenu";
import ScreenToolbar from "./components/screenToolbar";
import { ScreenInspectorPane } from "./components/screenInspectorPane";
import {
  ScreenCanvasSettings,
  ScreenElementPalette,
  ScreenStyleInspector,
} from "./components/screenEditorPanels";
import DashboardSubscriptionModal from "@/app/ops-analysis/components/dashboardSubscriptionModal";
import {
  addConfiguredScreenWidget,
  buildFiltersFromScreenItems,
  deleteScreenItem,
  getDefaultScreenWidgetAppearance,
  isScreenWidgetChartType,
  moveScreenItem,
  normalizeScreenWidgetAppearance,
  resolveScreenWidgetAppearance,
  resizeScreenItem,
  syncScreenFilterBindings,
  updateScreenItemConfig,
} from "./utils/layoutUtils";
import {
  createScreenChromeFromDrag,
  createScreenClockItem,
  createScreenDecorationItem,
  createScreenShapeItem,
  createScreenTextItem,
  createScreenTitleFrameItem,
  isScreenTitleFrameItem,
  isScreenWidgetItem,
  placeScreenItemAtPoint,
  type ScreenChromeDragPayload,
} from "./utils/screenItems";
import { copyScreenChromeItem } from "./utils/copyScreenItem";
import { copyScreenWidget } from "@/app/ops-analysis/utils/widgetCopy";
import {
  closeScreenFieldEdit,
  commitScreenEdit,
  confirmScreenHistory,
  createScreenEditSession,
  requestScreenHistory,
  screenHistoryShortcut,
  screenInspectorAfterReplace,
  screenItemFieldKey,
  type ScreenGeometryField,
  screenViewportFieldKey,
  screenViewSetsAfterResizeStop,
  syncScreenEditInspector,
  type ScreenEditDocument,
  type ScreenEditInspector,
  type ScreenEditSession,
  type ScreenHistoryAction,
} from "./utils/screenEditHistory";
import {
  moveScreenItemLayer,
  moveScreenItemToIndex,
  type ScreenLayerAction,
} from "./utils/screenLayer";
import {
  buildDefaultScreenViewSets,
  normalizeScreenViewSets,
  updateScreenViewport,
} from "./utils/viewport";
import ViewConfig from "@/app/ops-analysis/components/widgetConfig";
import ViewSelector from "@/app/ops-analysis/components/widgetSelector";
import { omitForeignChartTypeFields } from "@/app/ops-analysis/components/widgetConfig/utils/submitConfig";
import { useCanvasDraft } from "@/app/ops-analysis/hooks/useCanvasDraft";
import {
  restoreDraftRefreshInterval,
  toCanvasDraftResourceId,
  type CanvasDraftPayload,
} from "@/app/ops-analysis/api/canvasDraft";
import { bindCanvasDraftControls } from "@/app/ops-analysis/components/canvasDraftControls";
import { isSceneWidgetType } from "@/app/ops-analysis/types/sceneWidgetCapability";

export interface ScreenRef {
  hasUnsavedChanges: () => boolean;
}

interface ScreenQuerySnapshot {
  definitions: UnifiedFilterDefinition[];
  filterValues: Record<string, FilterValue>;
  appliedFilterValues: Record<string, FilterValue>;
  namespaceDraftId?: number;
  appliedNamespaceId?: number;
}

const screenWidgetDataKey = (item: ScreenWidgetItem) => {
  const { appearance: _appearance, ...dataConfig } = item.valueConfig ?? {};
  return JSON.stringify({
    id: item.id,
    title: item.title,
    chartType: item.chartType,
    dataConfig,
  });
};

const ScreenDataConfig = memo(
  function ScreenDataConfig({
    item,
    dataSourceManager,
    builtinNamespaceId,
    filterDefinitions,
    unifiedFilterValues,
    onDirtyChange,
    onConfirm,
    onClose,
  }: {
    item: LayoutItem;
    dataSourceManager: ReturnType<typeof useDataSourceManager>;
    builtinNamespaceId?: number;
    filterDefinitions?: UnifiedFilterDefinition[];
    unifiedFilterValues?: Record<string, FilterValue>;
    onDirtyChange?: (dirty: boolean) => void;
    onConfirm?: (values: WidgetConfig) => void;
    onClose?: () => void;
  }) {
    return (
      <ViewConfig
        open
        variant="panel"
        item={item}
        dataSourceManager={dataSourceManager}
        showChartThemeMode={false}
        surface="screen"
        builtinNamespaceId={builtinNamespaceId}
        filterDefinitions={filterDefinitions}
        unifiedFilterValues={unifiedFilterValues}
        onDirtyChange={onDirtyChange}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );
  },
  areScreenDataConfigPropsEqual,
);

const Screen = forwardRef<ScreenRef, ScreenProps>(({ selectedScreen, shareMode = false }, ref) => {
  const { t } = useTranslation();
  const { getScreenDetail, saveScreen } = useScreenApi();
  const { updateItem } = useDirectoryApi();
  const { hasPermission } = useBtnPermissions();
  const { shareLoading, openShare } = useCanvasShareAction('screen');
  const { namespaceList } = useOpsAnalysis();
  const shareOrganizationSeed = useShareOrganizationSeed();
  const dataSourceManager = useDataSourceManager();
  const { dataSources } = dataSourceManager;
  const { syncCanvasResources } = useCanvasResources();
  const queryState = useOpsAnalysisQueryState();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [historyNavEpoch, setHistoryNavEpoch] = useState(0);
  const [subscriptionModalVisible, setSubscriptionModalVisible] =
    useState(false);
  const [filterConfigOpen, setFilterConfigOpen] = useState(false);
  const [widgetSelectorOpen, setWidgetSelectorOpen] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [itemMenu, setItemMenu] = useState<{
    itemId: string;
    x: number;
    y: number;
  } | null>(null);
  const [inspectorTab, setInspectorTab] = useState<"style" | "data">("style");
  const [dataFormDirty, setDataFormDirty] = useState(false);
  const [pendingConfigItem, setPendingConfigItem] =
    useState<ComponentSelectorConfigItem | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [refreshCause, setRefreshCause] =
    useState<CanvasRuntimeRefreshCause>("initial");
  const [savedRefreshInterval, setSavedRefreshInterval] = useState(0);
  const [viewSets, setViewSets] = useState<ScreenViewSets>(
    buildDefaultScreenViewSets,
  );
  const [savedViewSets, setSavedViewSets] = useState<ScreenViewSets>(
    buildDefaultScreenViewSets,
  );
  const [draftViewSets, setDraftViewSetsState] = useState<ScreenViewSets>(
    buildDefaultScreenViewSets,
  );
  const draftViewSetsRef = useRef(draftViewSets);
  draftViewSetsRef.current = draftViewSets;
  const filtersRef = useRef(queryState.definitions);
  filtersRef.current = queryState.definitions;
  const sessionRef = useRef<ScreenEditSession | null>(null);
  const inspectorRef = useRef<ScreenEditInspector>({
    selectedItemId: null,
    inspectorTab: "style",
    dataConfigOpen: false,
  });
  const pendingResizeRef = useRef<{
    itemId: string;
    before: ScreenViewSets;
    size: { w: number; h: number };
  } | null>(null);
  const historyCommitRef = useRef<(document: ScreenEditDocument) => void>(() => {});
  inspectorRef.current = {
    selectedItemId,
    inspectorTab,
    dataConfigOpen: inspectorTab === "data" || pendingConfigItem != null,
  };
  const setDraftViewSets = useCallback((updater: SetStateAction<ScreenViewSets>) => {
    const next =
      typeof updater === "function"
        ? updater(draftViewSetsRef.current)
        : updater;
    draftViewSetsRef.current = next;
    setDraftViewSetsState(next);
  }, []);
  const [editQuerySnapshot, setEditQuerySnapshot] =
    useState<ScreenQuerySnapshot | null>(null);
  const { isFullscreen, enterFullscreen, exitFullscreen } =
    useAppViewFullscreen();

  const activeViewSets = editMode ? draftViewSets : viewSets;
  const selectedItem = useMemo(
    () => activeViewSets.items.find((item) => item.id === selectedItemId) ?? null,
    [activeViewSets.items, selectedItemId],
  );
  const currentConfigItem = useMemo(
    () =>
      selectedItem && isScreenWidgetItem(selectedItem) ? selectedItem : null,
    [selectedItem],
  );
  const currentConfigItemRef = useRef(currentConfigItem);
  currentConfigItemRef.current = currentConfigItem;
  const currentWidgetDataKey = currentConfigItem
    ? screenWidgetDataKey(currentConfigItem)
    : "";
  const currentViewConfigItem = useMemo<LayoutItem | null>(() => {
    const source = currentConfigItemRef.current;
    if (!source) return null;
    return {
      i: source.id,
      x: 0,
      y: 0,
      w: 1,
      h: 1,
      name: source.title || source.chartType,
      valueConfig: {
        ...source.valueConfig,
        chartType: source.chartType,
        appearance: normalizeScreenWidgetAppearance(
          source.valueConfig?.appearance,
        ),
      },
    };
  }, [currentWidgetDataKey]);
  const pendingViewConfigItem = useMemo(
    () =>
      pendingConfigItem
        ? {
          i: "",
          x: 0,
          y: 0,
          w: pendingConfigItem.defaultWidth,
          h: pendingConfigItem.defaultHeight,
          name: pendingConfigItem.name,
          description: pendingConfigItem.desc,
          valueConfig: {
            dataSource: pendingConfigItem.dataSource,
            chartType: pendingConfigItem.chartType,
            sceneWidgetType: pendingConfigItem.sceneWidgetType,
            appearance: getDefaultScreenWidgetAppearance(
              pendingConfigItem.chartType,
            ),
            dataSourceParams: [],
          },
        }
        : null,
    [pendingConfigItem],
  );
  const namespaceOptions = useMemo(() => {
    const namespaceIds = collectScreenNamespaceIds(activeViewSets, dataSources);
    if (namespaceIds.size === 0) return [];
    return namespaceList
      .filter((namespace) => namespaceIds.has(namespace.id))
      .map((namespace) => ({
        label: namespace.name || String(namespace.id),
        value: namespace.id,
      }));
  }, [activeViewSets, dataSources, namespaceList]);
  const namespaceSelectorElement = useMemo(() => {
    if (namespaceOptions.length <= 1) return undefined;
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-(--color-text-2) whitespace-nowrap">
          {t("namespace.title")}:
        </span>
        <Select
          value={queryState.namespaceDraftId}
          onChange={queryState.setNamespaceDraftId}
          options={namespaceOptions}
          style={{ minWidth: 160 }}
        />
      </div>
    );
  }, [
    namespaceOptions,
    queryState.namespaceDraftId,
    queryState.setNamespaceDraftId,
    t,
  ]);

  const hasUnsavedChanges = useCallback(
    () =>
      editMode &&
      JSON.stringify(draftViewSets) !== JSON.stringify(savedViewSets),
    [draftViewSets, editMode, savedViewSets],
  );

  const syncScreenCanvasResources = useCallback(
    (nextViewSets: ScreenViewSets) =>
      syncCanvasResources({
        source: nextViewSets,
        getDataSourceIds: collectScreenDataSourceIds,
        getNamespaceIds: collectScreenNamespaceIds,
      }),
    [syncCanvasResources],
  );

  const screenDraftResourceId = toCanvasDraftResourceId(selectedScreen?.data_id);
  const getScreenDraftPayload = useCallback(
    (): CanvasDraftPayload => ({
      name: selectedScreen?.name,
      desc: selectedScreen?.desc,
      view_sets: {
        ...draftViewSets,
        filters: queryState.definitions,
      },
      refresh_interval: savedRefreshInterval,
    }),
    [
      draftViewSets,
      queryState.definitions,
      savedRefreshInterval,
      selectedScreen?.desc,
      selectedScreen?.name,
    ],
  );
  const applyScreenDraftPayload = useCallback(
    (payload: CanvasDraftPayload) => {
      restoreDraftRefreshInterval(payload, setSavedRefreshInterval);
      const normalized = normalizeScreenViewSets(payload.view_sets);
      const loadedDefinitions = normalized.filters ?? [];
      historyCommitRef.current({
        viewSets: { ...normalized, filters: loadedDefinitions },
        filters: loadedDefinitions,
      });
      filtersRef.current = loadedDefinitions;
      queryState.resetQueryState({
        definitions: loadedDefinitions,
        organizationId: shareOrganizationSeed,
      });
      setRefreshVersion((current) => current + 1);
      setRefreshCause("manual");
      void syncScreenCanvasResources(normalized);
    },
    [queryState, setSavedRefreshInterval, shareOrganizationSeed, syncScreenCanvasResources],
  );
  const screenDraft = useCanvasDraft({
    resourceType: "screen",
    resourceId: screenDraftResourceId,
    enabled: Boolean(
      editMode &&
        !shareMode &&
        screenDraftResourceId &&
        !selectedScreen?.is_build_in,
    ),
    getPayload: getScreenDraftPayload,
    applyPayload: applyScreenDraftPayload,
  });

  useImperativeHandle(ref, () => ({
    hasUnsavedChanges,
  }));

  useEffect(() => {
    sessionRef.current = null;
    pendingResizeRef.current = null;
    setCanUndo(false);
    setCanRedo(false);
    const screenId = selectedScreen?.data_id;
    if (!screenId) {
      const emptyViewSets = buildDefaultScreenViewSets();
      setViewSets(emptyViewSets);
      setSavedViewSets(emptyViewSets);
      setDraftViewSets(emptyViewSets);
      setEditMode(false);
      setSelectedItemId(null);
      setPendingConfigItem(null);
      setEditQuerySnapshot(null);
      setRefreshVersion(0);
      setRefreshCause("initial");
      setSavedRefreshInterval(0);
      queryState.resetQueryState({
        definitions: emptyViewSets.filters ?? [],
        organizationId: shareOrganizationSeed,
      });
      return;
    }

    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const data = await getScreenDetail(screenId);
        if (cancelled) return;

        const normalized = normalizeScreenViewSets(data?.view_sets);
        await syncScreenCanvasResources(normalized);
        if (cancelled) return;

        setSavedRefreshInterval(
          normalizeCanvasRefreshInterval(data?.refresh_interval),
        );

        setViewSets(normalized);
        setSavedViewSets(normalized);
        setDraftViewSets(normalized);
        setEditMode(false);
        setSelectedItemId(null);
        setPendingConfigItem(null);
        setEditQuerySnapshot(null);
        queryState.resetQueryState({
          definitions: normalized.filters ?? [],
          organizationId: shareOrganizationSeed,
        });
      } catch (error) {
        console.error("Failed to load screen:", error);
        if (!cancelled) {
          const fallback = buildDefaultScreenViewSets();
          setViewSets(fallback);
          setSavedViewSets(fallback);
          setDraftViewSets(fallback);
          setEditMode(false);
          setSelectedItemId(null);
          setPendingConfigItem(null);
          setEditQuerySnapshot(null);
          queryState.resetQueryState({
            definitions: fallback.filters ?? [],
            organizationId: shareOrganizationSeed,
          });
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [
    getScreenDetail,
    queryState.resetQueryState,
    selectedScreen?.data_id,
    shareOrganizationSeed,
    syncScreenCanvasResources,
  ]);

  useEffect(() => {
    if (!selectedScreen?.data_id || !editMode) return;
    void syncScreenCanvasResources(activeViewSets);
  }, [activeViewSets, editMode, selectedScreen?.data_id, syncScreenCanvasResources]);

  useEffect(() => {
    if (namespaceOptions.length === 0) {
      queryState.setNamespaceDraftId(undefined);
      queryState.setAppliedNamespaceId(undefined);
      return;
    }

    const fallback = namespaceOptions[0]?.value;
    const hasDraft = namespaceOptions.some(
      (option) => option.value === queryState.namespaceDraftId,
    );
    const hasApplied = namespaceOptions.some(
      (option) => option.value === queryState.appliedNamespaceId,
    );

    if (!hasDraft) {
      queryState.setNamespaceDraftId(fallback);
    }
    if (!hasApplied) {
      queryState.setAppliedNamespaceId(fallback);
    }
  }, [
    namespaceOptions,
    queryState.appliedNamespaceId,
    queryState.namespaceDraftId,
    queryState.setAppliedNamespaceId,
    queryState.setNamespaceDraftId,
  ]);

  const projectDocument = useCallback((viewSets: ScreenViewSets): ScreenEditDocument => {
    const filters = buildFiltersFromScreenItems({
      viewSets,
      previousDefinitions: filtersRef.current,
      dataSources,
    });
    return {
      filters,
      viewSets: syncScreenFilterBindings(viewSets, filters, dataSources),
    };
  }, [dataSources]);

  const rememberSession = useCallback((next: ScreenEditSession) => {
    sessionRef.current = next;
    setDraftViewSets(next.document.viewSets);
    if (JSON.stringify(next.document.filters) !== JSON.stringify(filtersRef.current)) {
      filtersRef.current = next.document.filters;
      queryState.setDefinitions(next.document.filters);
    }
    setCanUndo(next.canUndo);
    setCanRedo(next.canRedo);
  }, [queryState.setDefinitions, setDraftViewSets]);

  const publishNavigation = useCallback((next: ScreenEditSession) => {
    rememberSession(next);
    setSelectedItemId(next.inspector.selectedItemId);
    setInspectorTab(next.inspector.inspectorTab);
    if (!next.inspector.dataConfigOpen) {
      setPendingConfigItem(null);
    }
    setHistoryNavEpoch((epoch) => epoch + 1);
  }, [rememberSession]);

  const syncedSession = useCallback(() => syncScreenEditInspector(
    sessionRef.current ?? createScreenEditSession(
      {
        viewSets: draftViewSetsRef.current,
        filters: filtersRef.current,
      },
      inspectorRef.current,
    ),
    inspectorRef.current,
  ), []);

  const endFieldEdit = useCallback(() => {
    if (!sessionRef.current) return;
    sessionRef.current = closeScreenFieldEdit(sessionRef.current);
  }, []);

  const commitDocument = useCallback((
    document: ScreenEditDocument,
    meta: { itemId?: string; fieldKey?: string | null } = {},
  ) => {
    pendingResizeRef.current = null;
    rememberSession(commitScreenEdit(syncedSession(), {
      document,
      itemId: meta.itemId,
      fieldKey: meta.fieldKey ?? undefined,
    }));
  }, [rememberSession, syncedSession]);

  historyCommitRef.current = (document) => {
    pendingResizeRef.current = null;
    const committed = commitScreenEdit(syncedSession(), { document });
    publishNavigation(syncScreenEditInspector(
      committed,
      screenInspectorAfterReplace(committed.inspector, committed.document),
    ));
  };

  const resetScreenHistory = useCallback((document?: ScreenEditDocument) => {
    pendingResizeRef.current = null;
    sessionRef.current = document
      ? createScreenEditSession(document, {
        selectedItemId: null,
        inspectorTab: "style",
        dataConfigOpen: false,
      })
      : null;
    setCanUndo(false);
    setCanRedo(false);
  }, []);

  const runAfterDataGuard = useCallback((
    next: () => void,
    onCancel?: () => void,
  ) => {
    if (!dataFormDirty) {
      next();
      return;
    }
    Modal.confirm({
      title: t("opsAnalysis.screen.unsavedDataTitle"),
      content: t("opsAnalysis.screen.unsavedDataContent"),
      centered: true,
      okText: t("common.confirm"),
      cancelText: t("common.cancel"),
      onOk: () => {
        setDataFormDirty(false);
        setPendingConfigItem(null);
        next();
      },
      onCancel,
    });
  }, [dataFormDirty, t]);

  const runScreenHistory = useCallback((action: ScreenHistoryAction) => {
    const current = sessionRef.current;
    if (!current) return;
    const synced = syncScreenEditInspector(current, inspectorRef.current);
    const request = requestScreenHistory(synced, action, dataFormDirty);
    if ('applied' in request) {
      if (request.applied) publishNavigation(request.session);
      return;
    }
    runAfterDataGuard(() => {
      const latest = sessionRef.current;
      if (!latest) return;
      publishNavigation(confirmScreenHistory(
        syncScreenEditInspector(latest, {
          ...inspectorRef.current,
          dataConfigOpen: false,
        }),
        action,
      ));
    });
  }, [dataFormDirty, publishNavigation, runAfterDataGuard]);

  const dataSourceResolver = useCallback(
    (dataSource?: string | number) =>
      dataSources.find((item) => String(item.id) === String(dataSource)),
    [dataSources],
  );

  const handleRefresh = useCallback(() => {
    setRefreshCause("manual");
    setRefreshVersion((current) => current + 1);
  }, []);

  const handlePeriodicRefresh = useCallback(
    (cause: CanvasRuntimeRefreshCause = "periodic") => {
      setRefreshCause(cause);
      setRefreshVersion((current) => current + 1);
    },
    [],
  );

  const canPersistRefreshInterval = canPersistCanvasRefreshInterval({
    shareMode,
    isBuiltIn: Boolean(selectedScreen?.is_build_in),
    hasEditPermission: hasPermission(["EditChart"]),
  });

  const { effectiveRefreshInterval, handleFrequencyChange } =
    useCanvasPeriodicRefresh({
      canvasId: selectedScreen?.data_id,
      savedInterval: savedRefreshInterval,
      canPersist: canPersistRefreshInterval,
      enabled: !editMode,
      patchRefreshInterval: async (interval) => {
        if (!selectedScreen?.data_id) {
          return;
        }
        await updateItem("screen", selectedScreen.data_id, {
          refresh_interval: interval,
        });
      },
      onPeriodicRefresh: handlePeriodicRefresh,
      onSavedIntervalChange: setSavedRefreshInterval,
    });

  const handleOpenNewWidgetConfig = useCallback(
    (item: ComponentSelectorConfigItem) => {
      setPendingConfigItem(item);
      setWidgetSelectorOpen(false);
      setSelectedItemId(null);
      setInspectorTab("data");
    },
    [],
  );

  const handleConfirmNewWidgetConfig = useCallback(
    (values: WidgetConfig) => {
      try {
        const nextViewSets = addConfiguredScreenWidget(draftViewSetsRef.current, values);
        const created = nextViewSets.items[nextViewSets.items.length - 1];
        commitDocument(projectDocument(nextViewSets), { itemId: created?.id });
        setPendingConfigItem(null);
        setDataFormDirty(false);
        setSelectedItemId(created?.id ?? null);
        setInspectorTab("style");
      } catch (error) {
        console.error("Failed to add screen widget:", error);
        message.error(t("opsAnalysis.screen.unsupportedWidgetType"));
      }
    },
    [commitDocument, projectDocument, t],
  );

  const handleMoveItem = useCallback(
    (itemId: string, position: { x: number; y: number }) => {
      const armed = pendingResizeRef.current;
      if (armed?.itemId === itemId) {
        pendingResizeRef.current = null;
        commitDocument({
          viewSets: screenViewSetsAfterResizeStop(
            armed.before,
            itemId,
            armed.size,
            position,
          ),
          filters: filtersRef.current,
        }, { itemId });
        return;
      }
      if (armed) {
        pendingResizeRef.current = null;
        commitDocument({
          viewSets: resizeScreenItem(armed.before, armed.itemId, armed.size),
          filters: filtersRef.current,
        }, { itemId: armed.itemId });
      }
      commitDocument({
        viewSets: moveScreenItem(draftViewSetsRef.current, itemId, position),
        filters: filtersRef.current,
      }, { itemId });
    },
    [commitDocument],
  );

  const handleResizeItem = useCallback(
    (itemId: string, size: { w: number; h: number }) => {
      const before = draftViewSetsRef.current;
      pendingResizeRef.current = { itemId, before, size };
      queueMicrotask(() => {
        const armed = pendingResizeRef.current;
        if (!armed || armed.itemId !== itemId || armed.before !== before) return;
        pendingResizeRef.current = null;
        commitDocument({
          viewSets: resizeScreenItem(before, itemId, size),
          filters: filtersRef.current,
        }, { itemId });
      });
    },
    [commitDocument],
  );

  const handleDeleteItem = useCallback(
    (itemId: string) => {
      commitDocument(
        projectDocument(deleteScreenItem(draftViewSetsRef.current, itemId)),
        { itemId },
      );
      setSelectedItemId((current) => (current === itemId ? null : current));
      setItemMenu(null);
    },
    [commitDocument, projectDocument],
  );

  const handleReorderItem = useCallback((itemId: string, toIndex: number) => {
    const current = draftViewSetsRef.current;
    commitDocument({
      viewSets: {
        ...current,
        items: moveScreenItemToIndex(current.items, itemId, toIndex),
      },
      filters: filtersRef.current,
    }, { itemId });
  }, [commitDocument]);

  const handleLayerAction = useCallback(
    (itemId: string, action: ScreenLayerAction) => {
      const current = draftViewSetsRef.current;
      commitDocument({
        viewSets: {
          ...current,
          items: moveScreenItemLayer(current.items, itemId, action),
        },
        filters: filtersRef.current,
      }, { itemId });
    },
    [commitDocument],
  );

  useEffect(() => {
    if (!editMode || shareMode) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Delete' && event.key !== 'Backspace') return;
      const target = event.target;
      if (target instanceof HTMLElement) {
        const tag = target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable) {
          return;
        }
        if (
          target.closest(
            '.ant-select, .ant-input, .ant-input-number, [contenteditable="true"]',
          )
        ) {
          return;
        }
      }
      if (!selectedItemId) return;
      event.preventDefault();
      handleDeleteItem(selectedItemId);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [editMode, handleDeleteItem, selectedItemId, shareMode]);

  useEffect(() => {
    if (!editMode || shareMode) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const action = screenHistoryShortcut(event, true);
      if (!action) return;
      event.preventDefault();
      runScreenHistory(action);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [editMode, runScreenHistory, shareMode]);

  const handleCopyItem = useCallback((itemId: string) => {
    const current = draftViewSetsRef.current;
    const copied = copyScreenWidget(current, itemId, { t })
      ?? copyScreenChromeItem(current, itemId);
    if (!copied) return;
    commitDocument(projectDocument(copied.viewSets), {
      itemId: copied.selectedItemId,
    });
    setSelectedItemId(copied.selectedItemId);
    setPendingConfigItem(null);
    setInspectorTab("style");
  }, [commitDocument, projectDocument, t]);

  const handleOpenItemConfig = useCallback((itemId: string) => {
    setSelectedItemId(itemId);
    setPendingConfigItem(null);
    setInspectorTab("data");
  }, []);

  const handleStartEdit = useCallback(() => {
    setDraftViewSets(viewSets);
    resetScreenHistory({
      viewSets: { ...viewSets, filters: queryState.definitions },
      filters: queryState.definitions,
    });
    setEditQuerySnapshot({
      definitions: queryState.definitions,
      filterValues: queryState.filterValues,
      appliedFilterValues: queryState.appliedFilterValues,
      namespaceDraftId: queryState.namespaceDraftId,
      appliedNamespaceId: queryState.appliedNamespaceId,
    });
    setEditMode(true);
    setSelectedItemId(null);
  }, [
    queryState.appliedFilterValues,
    queryState.appliedNamespaceId,
    queryState.definitions,
    queryState.filterValues,
    queryState.namespaceDraftId,
    viewSets,
    resetScreenHistory,
  ]);

  const handleCancelEdit = useCallback(() => {
    setDraftViewSets(savedViewSets);
    resetScreenHistory();
    queryState.resetQueryState(
      editQuerySnapshot ?? {
        definitions: savedViewSets.filters ?? [],
        filterValues: queryState.appliedFilterValues,
        appliedFilterValues: queryState.appliedFilterValues,
        namespaceDraftId: queryState.appliedNamespaceId,
        appliedNamespaceId: queryState.appliedNamespaceId,
      },
    );
    setEditQuerySnapshot(null);
    setEditMode(false);
    setSelectedItemId(null);
    setPendingConfigItem(null);
    setFilterConfigOpen(false);
  }, [
    editQuerySnapshot,
    queryState.appliedFilterValues,
    queryState.appliedNamespaceId,
    queryState.resetQueryState,
    savedViewSets,
    resetScreenHistory,
  ]);

  const handleSave = async () => {
    if (!selectedScreen?.data_id) return;

    const nextDraftViewSets = {
      ...draftViewSets,
      filters: queryState.definitions,
    };
    setSaving(true);
    try {
      await saveScreen(selectedScreen.data_id, {
        name: selectedScreen.name,
        desc: selectedScreen.desc,
        groups: selectedScreen.groups,
        view_sets: nextDraftViewSets,
      });
      setViewSets(nextDraftViewSets);
      setSavedViewSets(nextDraftViewSets);
      setDraftViewSets(nextDraftViewSets);
      queryState.setDefinitions(nextDraftViewSets.filters ?? []);
      setEditMode(false);
      setSelectedItemId(null);
      setPendingConfigItem(null);
      setEditQuerySnapshot(null);
      setFilterConfigOpen(false);
      resetScreenHistory();
      message.success(t("opsAnalysis.screen.saveSuccess"));
    } catch (error) {
      console.error("Failed to save screen:", error);
      message.error(t("opsAnalysis.screen.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleSaveSettings = ({
    viewport,
  }: {
    viewport: ScreenViewportConfig;
  }) => {
    const current = draftViewSetsRef.current;
    commitDocument({
      viewSets: updateScreenViewport(current, viewport),
      filters: filtersRef.current,
    }, {
      fieldKey: screenViewportFieldKey(current.viewport, viewport),
    });
  };

  const handleSelectCanvasItem = useCallback(
    (itemId: string | null) => {
      runAfterDataGuard(() => {
        setSelectedItemId(itemId);
        setPendingConfigItem(null);
        setInspectorTab("style");
        if (!itemId || typeof document === "undefined") return;
        window.requestAnimationFrame(() => {
          document
            .querySelector(`[data-screen-item-id="${CSS.escape(itemId)}"]`)
            ?.scrollIntoView({ block: "nearest", inline: "nearest" });
        });
      });
    },
    [runAfterDataGuard],
  );

  const openItemMenu = useCallback(
    (itemId: string, point: { x: number; y: number }) => {
      handleSelectCanvasItem(itemId);
      setItemMenu({ itemId, x: point.x, y: point.y });
    },
    [handleSelectCanvasItem],
  );

  const handleItemMenuAction = useCallback(
    (key: ScreenItemMenuKey) => {
      const itemId = itemMenu?.itemId;
      setItemMenu(null);
      if (!itemId) return;
      if (key === "edit") {
        handleOpenItemConfig(itemId);
        return;
      }
      if (key === "copy") {
        handleCopyItem(itemId);
        return;
      }
      if (key === "delete") {
        handleDeleteItem(itemId);
        return;
      }
      handleLayerAction(itemId, key);
    },
    [
      handleCopyItem,
      handleDeleteItem,
      handleLayerAction,
      handleOpenItemConfig,
      itemMenu?.itemId,
    ],
  );

  const itemMenuEntries = useMemo(() => {
    if (!itemMenu) return [];
    const target = draftViewSets.items.find((item) => item.id === itemMenu.itemId);
    if (!target) return [];
    return buildScreenItemMenu(target, draftViewSets.items, {
      shareMode,
      isBuiltIn: Boolean(selectedScreen?.is_build_in),
    });
  }, [
    draftViewSets.items,
    itemMenu,
    selectedScreen?.is_build_in,
    shareMode,
  ]);

  const handlePatchItem = useCallback((
    nextItem: ScreenItem,
    editedKey?: ScreenGeometryField,
  ) => {
    const current = draftViewSetsRef.current;
    const previous = current.items.find((item) => item.id === nextItem.id);
    commitDocument({
      viewSets: updateScreenItemConfig(current, nextItem.id, nextItem),
      filters: filtersRef.current,
    }, {
      itemId: nextItem.id,
      fieldKey: previous ? screenItemFieldKey(previous, nextItem, editedKey) : null,
    });
  }, [commitDocument]);

  const handleAddChromeItem = useCallback(
    (factory: (items: ScreenItem[]) => ScreenItem) => {
      runAfterDataGuard(() => {
        const current = draftViewSetsRef.current;
        const created = factory(current.items);
        commitDocument({
          viewSets: { ...current, items: [...current.items, created] },
          filters: filtersRef.current,
        }, { itemId: created.id });
        setPendingConfigItem(null);
        setSelectedItemId(created.id);
        setInspectorTab("style");
      });
    },
    [commitDocument, runAfterDataGuard],
  );

  const handleDropChrome = useCallback(
    (payload: ScreenChromeDragPayload, point: { x: number; y: number }) => {
      runAfterDataGuard(() => {
        const current = draftViewSetsRef.current;
        const created = placeScreenItemAtPoint(
          createScreenChromeFromDrag(current.items, payload),
          point,
          current.viewport,
        );
        if (isScreenTitleFrameItem(created)) {
          created.content = t(
            created.preset.startsWith("section")
              ? "opsAnalysis.screen.defaultSectionTitle"
              : "opsAnalysis.screen.defaultHeroTitle",
          );
        }
        commitDocument({
          viewSets: { ...current, items: [...current.items, created] },
          filters: filtersRef.current,
        }, { itemId: created.id });
        setPendingConfigItem(null);
        setSelectedItemId(created.id);
        setInspectorTab("style");
      });
    },
    [commitDocument, runAfterDataGuard, t],
  );

  const handleConfirmWidgetConfig = useCallback(
    (values: WidgetConfig) => {
      const currentConfigItem = currentConfigItemRef.current;
      if (!currentConfigItem) return;
      const nextChartType = isSceneWidgetType(values.sceneWidgetType)
        ? values.sceneWidgetType
        : values.chartType || currentConfigItem.chartType;

      if (!isScreenWidgetChartType(nextChartType)) {
        message.error(t("opsAnalysis.screen.unsupportedWidgetType"));
        return;
      }

      const nextItem = {
        ...currentConfigItem,
        chartType: nextChartType,
        title: values.name || currentConfigItem.title,
        valueConfig: omitForeignChartTypeFields(
          {
            ...currentConfigItem.valueConfig,
            ...values,
            chartType: nextChartType,
            appearance: resolveScreenWidgetAppearance(
              nextChartType,
              currentConfigItem.valueConfig?.appearance ?? values.appearance,
            ),
          },
          nextChartType,
        ),
      };
      commitDocument(
        projectDocument(updateScreenItemConfig(draftViewSetsRef.current, currentConfigItem.id, nextItem)),
        { itemId: currentConfigItem.id },
      );
      setDataFormDirty(false);
      message.success(t("opsAnalysis.screen.dataApplied"));
    },
    [commitDocument, projectDocument, t],
  );

  const handleDataConfigClose = useCallback(() => {
    setDataFormDirty(false);
    setPendingConfigItem((current) => {
      if (!current) return current;
      setInspectorTab("style");
      return null;
    });
  }, []);

  const handleTopologyLayoutChange = useCallback(
    (
      itemId: string,
      nextTopology: NonNullable<
        NonNullable<ScreenWidgetItem["valueConfig"]>["networkStatusTopology"]
      >,
    ) => {
      if (!editMode || shareMode) return;
      const current = draftViewSetsRef.current;
      commitDocument({
        viewSets: {
          ...current,
          items: current.items.map((item) =>
            item.id === itemId && isScreenWidgetItem(item)
              ? {
                ...item,
                valueConfig: {
                  ...item.valueConfig,
                  networkStatusTopology: nextTopology,
                },
              }
              : item,
          ),
        },
        filters: filtersRef.current,
      }, { itemId });
    },
    [commitDocument, editMode, shareMode],
  );

  const screenCanvas = useMemo(
    () => (
      <ScreenCanvas
        viewSets={activeViewSets}
        fullscreen={isFullscreen}
        editMode={editMode}
        shareMode={shareMode}
        selectedItemId={selectedItemId}
        refreshVersion={refreshVersion}
        refreshCause={refreshCause}
        screenId={selectedScreen?.data_id}
        dataSourceResolver={dataSourceResolver}
        filterDefinitions={queryState.definitions}
        unifiedFilterValues={queryState.appliedFilterValues}
        filterSearchVersion={queryState.filterSearchVersion}
        namespaceSearchVersion={queryState.namespaceSearchVersion}
        builtinNamespaceId={queryState.appliedNamespaceId}
        onSelectItem={handleSelectCanvasItem}
        onMoveItem={handleMoveItem}
        onResizeItem={handleResizeItem}
        onEditItem={handleOpenItemConfig}
        onOpenItemMenu={editMode && !shareMode ? openItemMenu : undefined}
        onDropChrome={editMode && !shareMode ? handleDropChrome : undefined}
        onTopologyLayoutChange={
          editMode && !shareMode ? handleTopologyLayoutChange : undefined
        }
      />
    ),
    [
      activeViewSets,
      dataSourceResolver,
      editMode,
      handleDropChrome,
      openItemMenu,
      handleOpenItemConfig,
      handleMoveItem,
      handleResizeItem,
      handleTopologyLayoutChange,
      queryState.appliedFilterValues,
      queryState.appliedNamespaceId,
      queryState.definitions,
      queryState.filterSearchVersion,
      queryState.namespaceSearchVersion,
      refreshVersion,
      refreshCause,
      handleSelectCanvasItem,
      isFullscreen,
      selectedItemId,
      selectedScreen?.data_id,
      shareMode,
    ],
  );

  const showFilterBar = queryState.definitions.length > 0;
  const editorOpen = editMode && !isFullscreen && !shareMode;
  const filterBarElement = showFilterBar ? (
    <UnifiedFilterBar
      definitions={queryState.definitions}
      values={queryState.filterValues}
      onChange={queryState.setFilterValues}
      onSearch={(values) =>
        queryState.applyQuery(values, queryState.namespaceDraftId)
      }
      onReset={(values) =>
        queryState.applyQuery(values, queryState.namespaceDraftId)
      }
      prefixContent={namespaceSelectorElement}
    />
  ) : null;
  const dataConfigItem = pendingViewConfigItem || currentViewConfigItem;
  const dataConfigPanel = dataConfigItem ? (
    <ScreenDataConfig
      key={historyNavEpoch}
      item={dataConfigItem}
      dataSourceManager={dataSourceManager}
      builtinNamespaceId={queryState.namespaceDraftId}
      filterDefinitions={queryState.definitions}
      unifiedFilterValues={queryState.filterValues}
      onDirtyChange={setDataFormDirty}
      onConfirm={
        pendingViewConfigItem
          ? handleConfirmNewWidgetConfig
          : handleConfirmWidgetConfig
      }
      onClose={handleDataConfigClose}
    />
  ) : null;

  return (
    <>
      <div
        className={
          isFullscreen
            ? "fixed inset-0 z-[1000] bg-slate-950"
            : "h-full min-h-0 w-full"
        }
      >
        <ViewWorkspace
          selectedItem={selectedScreen}
          loading={loading}
          titleFallback={t("opsAnalysis.screen.title")}
          emptyDescription={t("opsAnalysis.screen.selectFirst")}
          headerVisible={!isFullscreen}
          filterBarVisible={!isFullscreen}
          compactHeader
          flushContent={isFullscreen}
          contentClassName={isFullscreen ? "bg-slate-950" : undefined}
          toolbar={
            <ScreenToolbar
              selectedScreen={selectedScreen}
              editMode={editMode}
              shareMode={shareMode}
              shareLoading={shareLoading}
              onOpenShare={
                !shareMode && selectedScreen?.data_id
                  ? () => {
                    void openShare(selectedScreen.data_id);
                  }
                  : undefined
              }
              onOpenSubscription={
                !shareMode && selectedScreen?.data_id
                  ? () => setSubscriptionModalVisible(true)
                  : undefined
              }
              saving={saving}
              onRefresh={handleRefresh}
              frequenceValue={effectiveRefreshInterval}
              onFrequencyChange={handleFrequencyChange}
              onOpenSettings={() =>
                handleSelectCanvasItem(null)
              }
              onOpenFilterConfig={() => setFilterConfigOpen(true)}
              onPreview={enterFullscreen}
              onEdit={handleStartEdit}
              onCancel={() => runAfterDataGuard(handleCancelEdit)}
              onSave={() => runAfterDataGuard(() => { void handleSave(); })}
              canUndo={canUndo}
              canRedo={canRedo}
              onUndo={() => runScreenHistory("undo")}
              onRedo={() => runScreenHistory("redo")}
              editExtra={bindCanvasDraftControls({
                ...screenDraft,
                restoreFrame: (checkpointId) => new Promise<void>((resolve, reject) => {
                  runAfterDataGuard(
                    () => {
                      void screenDraft.restoreFrame(checkpointId).then(resolve, reject);
                    },
                    () => reject(new Error("screen-history-confirm-cancelled")),
                  );
                }),
              })}
            />
          }
          filterBar={filterBarElement}
        >
          {editorOpen ? (
            <div className="relative flex h-full min-h-0 overflow-hidden" data-screen-editor>
              <ScreenElementPalette
                selectedItemId={selectedItemId}
                items={draftViewSets.items}
                onSelectItem={handleSelectCanvasItem}
                onAddText={() =>
                  handleAddChromeItem((items) => createScreenTextItem(items))
                }
                onAddClock={() =>
                  handleAddChromeItem((items) => createScreenClockItem(items))
                }
                onAddTitleFrame={(preset: ScreenTitleFramePresetId) =>
                  handleAddChromeItem((items) =>
                    createScreenTitleFrameItem(items, {
                      preset,
                      content: t(
                        preset.startsWith("section")
                          ? "opsAnalysis.screen.defaultSectionTitle"
                          : "opsAnalysis.screen.defaultHeroTitle",
                      ),
                    }),
                  )
                }
                onAddDecoration={(
                  decorationType: ScreenDecorationType,
                  preset: ScreenDecorationPresetId,
                ) =>
                  handleAddChromeItem((items) =>
                    createScreenDecorationItem(items, decorationType, preset),
                  )
                }
                onAddShape={(shape: ScreenShapeKind) =>
                  handleAddChromeItem((items) => createScreenShapeItem(items, shape))
                }
                onOpenChartSelector={() => setWidgetSelectorOpen(true)}
                onOpenItemMenu={openItemMenu}
                onReorderItem={handleReorderItem}
              />
              <div className="min-h-0 min-w-0 flex-1">{screenCanvas}</div>
              <ScreenInspectorPane
                label={t("opsAnalysis.screen.inspectorResize")}
                onBlur={(event) => {
                  const currentTarget = event.target instanceof Element ? event.target : null;
                  const field = currentTarget?.closest("input, textarea");
                  if (!field) return;
                  const nextTarget = event.relatedTarget instanceof Element ? event.relatedTarget : null;
                  if (nextTarget && (nextTarget === field || field.contains(nextTarget))) return;
                  if (sessionRef.current) {
                    sessionRef.current = closeScreenFieldEdit(sessionRef.current);
                  }
                }}
              >
                {pendingConfigItem ? (
                  <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                    <div className="border-b border-(--color-border-1) px-3 py-2 text-sm font-semibold text-(--color-text-1)">
                      {t("opsAnalysis.screen.dataTab")}
                    </div>
                    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                      {dataConfigPanel}
                    </div>
                  </div>
                ) : currentConfigItem ? (
                  <Tabs
                    className="flex min-h-0 flex-1 flex-col [&_.ant-tabs-content]:h-full [&_.ant-tabs-content-holder]:min-h-0 [&_.ant-tabs-content-holder]:flex-1 [&_.ant-tabs-content-holder]:overflow-hidden [&_.ant-tabs-nav]:mb-0 [&_.ant-tabs-nav-wrap]:px-3 [&_.ant-tabs-tabpane]:m-0 [&_.ant-tabs-tabpane]:h-full [&_.ant-tabs-tabpane]:min-h-0 [&_.ant-tabs-tabpane]:overflow-hidden"
                    activeKey={inspectorTab}
                    onChange={(key) => setInspectorTab(key as "style" | "data")}
                    items={[
                      {
                        key: "style",
                        label: t("opsAnalysis.screen.styleTab"),
                        children: selectedItem ? (
                          <ScreenStyleInspector
                            item={selectedItem}
                            viewport={draftViewSets.viewport}
                            onChange={handlePatchItem}
                            onFieldEditEnd={endFieldEdit}
                          />
                        ) : null,
                      },
                      {
                        key: "data",
                        label: t("opsAnalysis.screen.dataTab"),
                        children: (
                          <div className="flex h-full min-h-0 flex-col overflow-hidden">
                            {dataConfigPanel}
                          </div>
                        ),
                      },
                    ]}
                  />
                ) : selectedItem ? (
                  <ScreenStyleInspector
                    item={selectedItem}
                    viewport={draftViewSets.viewport}
                    onChange={handlePatchItem}
                    onFieldEditEnd={endFieldEdit}
                  />
                ) : (
                  <>
                    <div className="border-b border-(--color-border-1) px-3 py-2 text-sm font-semibold text-(--color-text-1)">
                      {t("opsAnalysis.screen.canvasSettings")}
                    </div>
                    <ScreenCanvasSettings
                      viewport={draftViewSets.viewport}
                      onChange={(viewport) => handleSaveSettings({ viewport })}
                      onFieldEditEnd={endFieldEdit}
                    />
                  </>
                )}
              </ScreenInspectorPane>
              {itemMenu && itemMenuEntries.length > 0 ? (
                <ScreenItemContextMenu
                  open
                  x={itemMenu.x}
                  y={itemMenu.y}
                  entries={itemMenuEntries}
                  onAction={handleItemMenuAction}
                  onClose={() => setItemMenu(null)}
                />
              ) : null}
            </div>
          ) : (
            screenCanvas
          )}
        </ViewWorkspace>
      </div>
      <ViewSelector
        visible={widgetSelectorOpen}
        onCancel={() => setWidgetSelectorOpen(false)}
        onOpenConfig={handleOpenNewWidgetConfig}
        surface="screen"
      />
      <UnifiedFilterConfigModal
        open={filterConfigOpen}
        onCancel={() => setFilterConfigOpen(false)}
        onConfirm={(definitions) => {
          const nextViewSets = syncScreenFilterBindings(
            {
              ...draftViewSetsRef.current,
              filters: definitions,
            },
            definitions,
            dataSources,
          );
          commitDocument({ viewSets: nextViewSets, filters: definitions });
          setFilterConfigOpen(false);
        }}
        definitions={queryState.definitions}
        layoutItems={draftViewSets.items.filter(isScreenWidgetItem).map((item) => ({
          i: item.id,
          x: item.x,
          y: item.y,
          w: item.w,
          h: item.h,
          name: item.title,
          valueConfig: item.valueConfig,
        }))}
        dataSources={dataSources}
      />
      {selectedScreen?.data_id != null && (
        <DashboardSubscriptionModal
          open={subscriptionModalVisible}
          resourceType="screen"
          resourceId={Number(selectedScreen.data_id)}
          appliedFilterValues={queryState.appliedFilterValues}
          onClose={() => setSubscriptionModalVisible(false)}
        />
      )}
    </>
  );
});

Screen.displayName = "Screen";

export default Screen;
