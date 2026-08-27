"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from "react";
import { message, Select } from "antd";
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
import { useCanvasResources } from "@/app/ops-analysis/hooks/useCanvasResources";
import { useDataSourceManager } from "@/app/ops-analysis/hooks/useDataSource";
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
  ScreenDecorationsConfig,
  ScreenProps,
  ScreenViewSets,
  ScreenViewportConfig,
  ScreenWidgetItem,
} from "@/app/ops-analysis/types/screen";
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from "@/app/ops-analysis/components/appFullscreen";
import ViewWorkspace from "../components/viewWorkspace";
import ScreenCanvas from "./components/screenCanvas";
import ScreenConfigModal from "./components/screenConfigModal";
import ScreenToolbar from "./components/screenToolbar";
import DashboardSubscriptionModal from "@/app/ops-analysis/components/dashboardSubscriptionModal";
import {
  addConfiguredScreenWidget,
  buildFiltersFromScreenItems,
  canViewportContainItems,
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

const Screen = forwardRef<ScreenRef, ScreenProps>(({ selectedScreen, shareMode = false }, ref) => {
  const { t } = useTranslation();
  const { getScreenDetail, saveScreen } = useScreenApi();
  const { updateItem } = useDirectoryApi();
  const { hasPermission } = useBtnPermissions();
  const { shareLoading, openShare } = useCanvasShareAction('screen');
  const { namespaceList } = useOpsAnalysis();
  const dataSourceManager = useDataSourceManager();
  const { dataSources } = dataSourceManager;
  const { syncCanvasResources } = useCanvasResources();
  const queryState = useOpsAnalysisQueryState();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [subscriptionModalVisible, setSubscriptionModalVisible] =
    useState(false);
  const [filterConfigOpen, setFilterConfigOpen] = useState(false);
  const [widgetSelectorOpen, setWidgetSelectorOpen] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [configItemId, setConfigItemId] = useState<string | null>(null);
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
  const [draftViewSets, setDraftViewSets] = useState<ScreenViewSets>(
    buildDefaultScreenViewSets,
  );
  const [editQuerySnapshot, setEditQuerySnapshot] =
    useState<ScreenQuerySnapshot | null>(null);
  const { isFullscreen, enterFullscreen, exitFullscreen } =
    useAppViewFullscreen();

  const activeViewSets = editMode ? draftViewSets : viewSets;
  const currentConfigItem = useMemo(
    () => draftViewSets.items.find((item) => item.id === configItemId),
    [configItemId, draftViewSets.items],
  );
  const currentViewConfigItem = useMemo<LayoutItem | null>(
    () =>
      currentConfigItem
        ? {
          i: currentConfigItem.id,
          x: 0,
          y: 0,
          w: 1,
          h: 1,
          name: currentConfigItem.title || currentConfigItem.chartType,
          valueConfig: {
            ...currentConfigItem.valueConfig,
            chartType: currentConfigItem.chartType,
            appearance: normalizeScreenWidgetAppearance(
              currentConfigItem.valueConfig?.appearance,
            ),
          },
        }
        : null,
    [currentConfigItem],
  );
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

      setDraftViewSets({
        ...normalized,
        filters: loadedDefinitions,
      });
      queryState.resetQueryState({ definitions: loadedDefinitions });
      setRefreshVersion((current) => current + 1);
      setRefreshCause("manual");
      void syncScreenCanvasResources(normalized);
    },
    [queryState, setSavedRefreshInterval, syncScreenCanvasResources],
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
    const screenId = selectedScreen?.data_id;
    if (!screenId) {
      const emptyViewSets = buildDefaultScreenViewSets();
      setViewSets(emptyViewSets);
      setSavedViewSets(emptyViewSets);
      setDraftViewSets(emptyViewSets);
      setEditMode(false);
      setSelectedItemId(null);
      setConfigItemId(null);
      setPendingConfigItem(null);
      setEditQuerySnapshot(null);
      setRefreshVersion(0);
      setRefreshCause("initial");
      setSavedRefreshInterval(0);
      queryState.resetQueryState({
        definitions: emptyViewSets.filters ?? [],
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
        setConfigItemId(null);
        setPendingConfigItem(null);
        setEditQuerySnapshot(null);
        queryState.resetQueryState({
          definitions: normalized.filters ?? [],
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
          setConfigItemId(null);
          setPendingConfigItem(null);
          setEditQuerySnapshot(null);
          queryState.resetQueryState({
            definitions: fallback.filters ?? [],
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

  const rebuildDraftFilters = useCallback(
    (nextViewSets: ScreenViewSets) => {
      const nextDefinitions = buildFiltersFromScreenItems({
        viewSets: nextViewSets,
        previousDefinitions: queryState.definitions,
        dataSources,
      });
      queryState.setDefinitions(nextDefinitions);
      return syncScreenFilterBindings(
        nextViewSets,
        nextDefinitions,
        dataSources,
      );
    },
    [dataSources, queryState.definitions, queryState.setDefinitions],
  );

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
      setConfigItemId(null);
    },
    [],
  );

  const handleConfirmNewWidgetConfig = useCallback(
    (values: WidgetConfig) => {
      try {
        setDraftViewSets((current) =>
          rebuildDraftFilters(addConfiguredScreenWidget(current, values)),
        );
        setPendingConfigItem(null);
      } catch (error) {
        console.error("Failed to add screen widget:", error);
        message.error(t("opsAnalysis.screen.unsupportedWidgetType"));
      }
    },
    [rebuildDraftFilters, t],
  );

  const handleMoveItem = useCallback(
    (itemId: string, position: { x: number; y: number }) => {
      setDraftViewSets((current) => moveScreenItem(current, itemId, position));
    },
    [],
  );

  const handleResizeItem = useCallback(
    (itemId: string, size: { w: number; h: number }) => {
      setDraftViewSets((current) => resizeScreenItem(current, itemId, size));
    },
    [],
  );

  const handleDeleteItem = useCallback(
    (itemId: string) => {
      setDraftViewSets((current) =>
        rebuildDraftFilters(deleteScreenItem(current, itemId)),
      );
      setSelectedItemId((current) => (current === itemId ? null : current));
      setConfigItemId((current) => (current === itemId ? null : current));
    },
    [rebuildDraftFilters],
  );

  const handleOpenItemConfig = useCallback((itemId: string) => {
    setSelectedItemId(itemId);
    setConfigItemId(itemId);
  }, []);

  const handleStartEdit = useCallback(() => {
    setDraftViewSets(viewSets);
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
  ]);

  const handleCancelEdit = useCallback(() => {
    setDraftViewSets(savedViewSets);
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
    setConfigItemId(null);
    setPendingConfigItem(null);
    setFilterConfigOpen(false);
  }, [
    editQuerySnapshot,
    queryState.appliedFilterValues,
    queryState.appliedNamespaceId,
    queryState.resetQueryState,
    savedViewSets,
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
      setConfigItemId(null);
      setPendingConfigItem(null);
      setEditQuerySnapshot(null);
      setFilterConfigOpen(false);
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
    decorations,
  }: {
    viewport: ScreenViewportConfig;
    decorations: ScreenDecorationsConfig;
  }) => {
    setDraftViewSets((current) => ({
      ...updateScreenViewport(current, viewport),
      decorations: {
        ...current.decorations,
        ...decorations,
      },
    }));
    setSettingsOpen(false);
  };

  const canSaveViewport = useCallback(
    (viewport: ScreenViewportConfig) =>
      canViewportContainItems(activeViewSets.items, viewport),
    [activeViewSets.items],
  );

  const handleConfirmWidgetConfig = useCallback(
    (values: WidgetConfig) => {
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
              values.appearance,
            ),
          },
          nextChartType,
        ),
      };
      setDraftViewSets((current) =>
        rebuildDraftFilters(
          updateScreenItemConfig(current, currentConfigItem.id, nextItem),
        ),
      );
      setConfigItemId(null);
    },
    [currentConfigItem, rebuildDraftFilters, t],
  );

  const handleTopologyLayoutChange = useCallback(
    (
      itemId: string,
      nextTopology: NonNullable<
        NonNullable<ScreenWidgetItem["valueConfig"]>["networkStatusTopology"]
      >,
    ) => {
      if (!editMode || shareMode) return;
      setDraftViewSets((current) => ({
        ...current,
        items: current.items.map((item) =>
          item.id === itemId
            ? {
              ...item,
              valueConfig: {
                ...item.valueConfig,
                networkStatusTopology: nextTopology,
              },
            }
            : item,
        ),
      }));
    },
    [editMode, shareMode],
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
        onSelectItem={setSelectedItemId}
        onMoveItem={handleMoveItem}
        onResizeItem={handleResizeItem}
        onEditItem={handleOpenItemConfig}
        onDeleteItem={handleDeleteItem}
        onTopologyLayoutChange={
          editMode && !shareMode ? handleTopologyLayoutChange : undefined
        }
      />
    ),
    [
      activeViewSets,
      dataSourceResolver,
      editMode,
      handleDeleteItem,
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
      isFullscreen,
      selectedItemId,
      selectedScreen?.data_id,
      shareMode,
    ],
  );

  return (
    <>
      <div
        className={
          isFullscreen
            ? "fixed inset-0 z-[1000] bg-slate-950"
            : "h-full min-h-0 w-full"
        }
      >
        <AppViewFullscreenExit visible={isFullscreen} onExit={exitFullscreen} />
        <ViewWorkspace
          selectedItem={selectedScreen}
          loading={loading}
          titleFallback={t("opsAnalysis.screen.title")}
          emptyDescription={t("opsAnalysis.screen.selectFirst")}
          headerVisible={!isFullscreen}
          filterBarVisible={!isFullscreen}
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
              onOpenSettings={() => setSettingsOpen(true)}
              onOpenFilterConfig={() => setFilterConfigOpen(true)}
              onOpenWidgetSelector={() => setWidgetSelectorOpen(true)}
              onPreview={enterFullscreen}
              onEdit={handleStartEdit}
              onCancel={handleCancelEdit}
              onSave={handleSave}
              editExtra={bindCanvasDraftControls(screenDraft)}
            />
          }
          filterBar={
            (queryState.definitions.length > 0 ||
              namespaceSelectorElement ||
              editMode) && (
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
            )
          }
        >
          {screenCanvas}
        </ViewWorkspace>
      </div>
      <ViewSelector
        visible={widgetSelectorOpen}
        onCancel={() => setWidgetSelectorOpen(false)}
        onOpenConfig={handleOpenNewWidgetConfig}
        surface="screen"
      />
      <ScreenConfigModal
        open={settingsOpen}
        viewport={activeViewSets.viewport}
        decorations={activeViewSets.decorations}
        saving={saving}
        canSaveViewport={canSaveViewport}
        onCancel={() => setSettingsOpen(false)}
        onSave={handleSaveSettings}
      />
      <UnifiedFilterConfigModal
        open={filterConfigOpen}
        onCancel={() => setFilterConfigOpen(false)}
        onConfirm={(definitions) => {
          const nextViewSets = syncScreenFilterBindings(
            {
              ...draftViewSets,
              filters: definitions,
            },
            definitions,
            dataSources,
          );
          setDraftViewSets(nextViewSets);
          queryState.applyFilterConfigConfirm(definitions);
          setFilterConfigOpen(false);
        }}
        definitions={queryState.definitions}
        layoutItems={draftViewSets.items.map((item) => ({
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
      {currentViewConfigItem && (
        <ViewConfig
          open={Boolean(configItemId)}
          item={currentViewConfigItem}
          dataSourceManager={dataSourceManager}
          showChartThemeMode={false}
          surface="screen"
          builtinNamespaceId={queryState.namespaceDraftId}
          filterDefinitions={queryState.definitions}
          unifiedFilterValues={queryState.filterValues}
          onConfirm={handleConfirmWidgetConfig}
          onClose={() => setConfigItemId(null)}
        />
      )}
      {pendingViewConfigItem && (
        <ViewConfig
          open={Boolean(pendingConfigItem)}
          item={pendingViewConfigItem}
          dataSourceManager={dataSourceManager}
          showChartThemeMode={false}
          surface="screen"
          builtinNamespaceId={queryState.namespaceDraftId}
          filterDefinitions={queryState.definitions}
          unifiedFilterValues={queryState.filterValues}
          onConfirm={handleConfirmNewWidgetConfig}
          onClose={() => setPendingConfigItem(null)}
        />
      )}
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
