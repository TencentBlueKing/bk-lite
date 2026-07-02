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
import {
  UnifiedFilterBar,
  UnifiedFilterConfigModal,
} from "@/app/ops-analysis/components/unifiedFilter";
import { useOpsAnalysis } from "@/app/ops-analysis/context/common";
import { useDataSourceManager } from "@/app/ops-analysis/hooks/useDataSource";
import { useOpsAnalysisQueryState } from "@/app/ops-analysis/hooks/useOpsAnalysisQueryState";
import {
  collectScreenDataSourceIds,
  collectScreenNamespaceIds,
} from "@/app/ops-analysis/utils/canvasResources";
import type {
  ComponentSelectorConfigItem,
  FilterValue,
  UnifiedFilterDefinition,
  WidgetConfig,
} from "@/app/ops-analysis/types/dashBoard";
import type {
  ScreenDecorationsConfig,
  ScreenProps,
  ScreenViewSets,
  ScreenViewportConfig,
} from "@/app/ops-analysis/types/screen";
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from "@/app/ops-analysis/components/appFullscreen";
import ViewWorkspace from "../components/viewWorkspace";
import ScreenCanvas from "./components/screenCanvas";
import ScreenConfigModal from "./components/screenConfigModal";
import ScreenToolbar from "./components/screenToolbar";
import {
  addConfiguredScreenWidget,
  buildFiltersFromScreenItems,
  canViewportContainItems,
  deleteScreenItem,
  isScreenWidgetChartType,
  moveScreenItem,
  resizeScreenItem,
  syncScreenFilterBindings,
  updateScreenItemConfig,
} from "./utils/layout";
import {
  buildDefaultScreenViewSets,
  normalizeScreenViewSets,
  updateScreenViewport,
} from "./utils/viewport";
import ViewConfig from "@/app/ops-analysis/components/widgetConfig";
import ViewSelector from "@/app/ops-analysis/components/widgetSelector";

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

const Screen = forwardRef<ScreenRef, ScreenProps>(({ selectedScreen }, ref) => {
  const { t } = useTranslation();
  const { getScreenDetail, saveScreen } = useScreenApi();
  const { namespaceList } = useOpsAnalysis();
  const dataSourceManager = useDataSourceManager();
  const { dataSources, loadCanvasDataSources } = dataSourceManager;
  const queryState = useOpsAnalysisQueryState();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [filterConfigOpen, setFilterConfigOpen] = useState(false);
  const [widgetSelectorOpen, setWidgetSelectorOpen] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [configItemId, setConfigItemId] = useState<string | null>(null);
  const [pendingConfigItem, setPendingConfigItem] =
    useState<ComponentSelectorConfigItem | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
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
      queryState.resetQueryState({
        definitions: emptyViewSets.filters ?? [],
      });
      return;
    }

    let cancelled = false;
    setLoading(true);
    getScreenDetail(screenId)
      .then((data) => {
        if (cancelled) return;

        const normalized = normalizeScreenViewSets(data?.view_sets);
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
      })
      .catch((error) => {
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
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [getScreenDetail, queryState.resetQueryState, selectedScreen?.data_id]);

  useEffect(() => {
    if (!selectedScreen?.data_id) return;
    void loadCanvasDataSources(collectScreenDataSourceIds(activeViewSets));
  }, [activeViewSets, loadCanvasDataSources, selectedScreen?.data_id]);

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
    setRefreshVersion((current) => current + 1);
  }, []);

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
      const nextChartType =
        values.sceneWidgetType === "networkStatusTopology"
          ? "networkStatusTopology"
          : values.chartType || currentConfigItem.chartType;

      if (!isScreenWidgetChartType(nextChartType)) {
        message.error(t("opsAnalysis.screen.unsupportedWidgetType"));
        return;
      }

      const nextItem = {
        ...currentConfigItem,
        chartType: nextChartType,
        title: values.name || currentConfigItem.title,
        valueConfig: {
          ...currentConfigItem.valueConfig,
          ...values,
          chartType: nextChartType,
          chartThemeMode: "screen-dark" as const,
        },
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

  const screenCanvas = useMemo(
    () => (
      <ScreenCanvas
        viewSets={activeViewSets}
        editMode={editMode}
        selectedItemId={selectedItemId}
        refreshVersion={refreshVersion}
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
      queryState.appliedFilterValues,
      queryState.appliedNamespaceId,
      queryState.definitions,
      queryState.filterSearchVersion,
      queryState.namespaceSearchVersion,
      refreshVersion,
      selectedItemId,
      selectedScreen?.data_id,
    ],
  );

  if (isFullscreen) {
    return (
      <div className="fixed inset-0 z-[1000] bg-slate-950">
        <AppViewFullscreenExit visible onExit={exitFullscreen} />
        <ScreenCanvas
          viewSets={activeViewSets}
          fullscreen
          refreshVersion={refreshVersion}
          screenId={selectedScreen?.data_id}
          dataSourceResolver={dataSourceResolver}
          filterDefinitions={queryState.definitions}
          unifiedFilterValues={queryState.appliedFilterValues}
          filterSearchVersion={queryState.filterSearchVersion}
          namespaceSearchVersion={queryState.namespaceSearchVersion}
          builtinNamespaceId={queryState.appliedNamespaceId}
        />
      </div>
    );
  }

  return (
    <>
      <ViewWorkspace
        selectedItem={selectedScreen}
        loading={loading}
        titleFallback={t("opsAnalysis.screen.title")}
        emptyDescription={t("opsAnalysis.screen.selectFirst")}
        toolbar={
          <ScreenToolbar
            selectedScreen={selectedScreen}
            editMode={editMode}
            saving={saving}
            onRefresh={handleRefresh}
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenFilterConfig={() => setFilterConfigOpen(true)}
            onOpenWidgetSelector={() => setWidgetSelectorOpen(true)}
            onPreview={enterFullscreen}
            onEdit={handleStartEdit}
            onCancel={handleCancelEdit}
            onSave={handleSave}
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
      <ViewSelector
        visible={widgetSelectorOpen}
        onCancel={() => setWidgetSelectorOpen(false)}
        onOpenConfig={handleOpenNewWidgetConfig}
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
          queryState.setDefinitions(definitions);
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
      {currentConfigItem && (
        <ViewConfig
          open={Boolean(configItemId)}
          item={{
            i: currentConfigItem.id,
            x: 0,
            y: 0,
            w: 1,
            h: 1,
            name: currentConfigItem.title || currentConfigItem.chartType,
            valueConfig: {
              ...currentConfigItem.valueConfig,
              chartType: currentConfigItem.chartType,
              chartThemeMode: "screen-dark",
            },
          }}
          dataSourceManager={dataSourceManager}
          showChartThemeMode={false}
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
          builtinNamespaceId={queryState.namespaceDraftId}
          filterDefinitions={queryState.definitions}
          unifiedFilterValues={queryState.filterValues}
          onConfirm={handleConfirmNewWidgetConfig}
          onClose={() => setPendingConfigItem(null)}
        />
      )}
    </>
  );
});

Screen.displayName = "Screen";

export default Screen;
