"use client";

import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from "react";
import { message } from "antd";
import { useTranslation } from "@/utils/i18n";
import { useScreenApi } from "@/app/ops-analysis/api/screen";
import { useDataSourceManager } from "@/app/ops-analysis/hooks/useDataSource";
import type {
  ComponentSelectorConfigItem,
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
import CanvasWorkspace from "../components/canvasWorkspace";
import ScreenCanvas from "./components/screenCanvas";
import ScreenConfigModal from "./components/screenConfigModal";
import ScreenToolbar from "./components/screenToolbar";
import {
  addConfiguredScreenWidget,
  canViewportContainItems,
  collectScreenDataSourceIds,
  deleteScreenItem,
  isScreenWidgetChartType,
  moveScreenItem,
  resizeScreenItem,
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

const Screen = forwardRef<ScreenRef, ScreenProps>(({ selectedScreen }, ref) => {
  const { t } = useTranslation();
  const { getScreenDetail, saveScreen } = useScreenApi();
  const dataSourceManager = useDataSourceManager();
  const { dataSources, loadCanvasDataSources } = dataSourceManager;
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
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
  }, [getScreenDetail, selectedScreen?.data_id]);

  useEffect(() => {
    if (!selectedScreen?.data_id) return;
    void loadCanvasDataSources(collectScreenDataSourceIds(activeViewSets));
  }, [activeViewSets, loadCanvasDataSources, selectedScreen?.data_id]);

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
          addConfiguredScreenWidget(current, values),
        );
        setPendingConfigItem(null);
      } catch (error) {
        console.error("Failed to add screen widget:", error);
        message.error(t("opsAnalysis.screen.unsupportedWidgetType"));
      }
    },
    [t],
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

  const handleDeleteItem = useCallback((itemId: string) => {
    setDraftViewSets((current) => deleteScreenItem(current, itemId));
    setSelectedItemId((current) => (current === itemId ? null : current));
    setConfigItemId((current) => (current === itemId ? null : current));
  }, []);

  const handleOpenItemConfig = useCallback((itemId: string) => {
    setSelectedItemId(itemId);
    setConfigItemId(itemId);
  }, []);

  const handleStartEdit = useCallback(() => {
    setDraftViewSets(viewSets);
    setEditMode(true);
    setSelectedItemId(null);
  }, [viewSets]);

  const handleCancelEdit = useCallback(() => {
    setDraftViewSets(savedViewSets);
    setEditMode(false);
    setSelectedItemId(null);
    setConfigItemId(null);
    setPendingConfigItem(null);
  }, [savedViewSets]);

  const handleSave = async () => {
    if (!selectedScreen?.data_id) return;

    setSaving(true);
    try {
      await saveScreen(selectedScreen.data_id, {
        name: selectedScreen.name,
        desc: selectedScreen.desc,
        groups: selectedScreen.groups,
        view_sets: draftViewSets,
      });
      setViewSets(draftViewSets);
      setSavedViewSets(draftViewSets);
      setEditMode(false);
      setSelectedItemId(null);
      setConfigItemId(null);
      setPendingConfigItem(null);
      message.success(t("opsAnalysis.screen.saveSuccess"));
    } catch (error) {
      console.error("Failed to save screen:", error);
      message.error(t("opsAnalysis.screen.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleSaveSettings = async ({
    viewport,
    decorations,
  }: {
    viewport: ScreenViewportConfig;
    decorations: ScreenDecorationsConfig;
  }) => {
    const applySettings = (current: ScreenViewSets): ScreenViewSets => ({
      ...updateScreenViewport(current, viewport),
      decorations: {
        ...current.decorations,
        ...decorations,
      },
    });

    if (editMode) {
      setDraftViewSets((current) => applySettings(current));
      setSettingsOpen(false);
      return;
    }

    if (!selectedScreen?.data_id) return;
    const nextViewSets = applySettings(viewSets);
    setSaving(true);
    try {
      await saveScreen(selectedScreen.data_id, {
        name: selectedScreen.name,
        desc: selectedScreen.desc,
        groups: selectedScreen.groups,
        view_sets: nextViewSets,
      });
      setViewSets(nextViewSets);
      setSavedViewSets(nextViewSets);
      setDraftViewSets(nextViewSets);
      setSettingsOpen(false);
      message.success(t("opsAnalysis.screen.saveSuccess"));
    } catch (error) {
      console.error("Failed to save screen settings:", error);
      message.error(t("opsAnalysis.screen.saveFailed"));
    } finally {
      setSaving(false);
    }
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
        config: {
          ...currentConfigItem.config,
          ...values,
          chartType: nextChartType,
          chartThemeMode: "screen-dark" as const,
        },
      };
      setDraftViewSets((current) =>
        updateScreenItemConfig(current, currentConfigItem.id, nextItem),
      );
      setConfigItemId(null);
    },
    [currentConfigItem, t],
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
      handleMoveItem,
      handleResizeItem,
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
        />
      </div>
    );
  }

  return (
    <>
      <CanvasWorkspace
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
            onOpenWidgetSelector={() => setWidgetSelectorOpen(true)}
            onPreview={enterFullscreen}
            onEdit={handleStartEdit}
            onCancel={handleCancelEdit}
            onSave={handleSave}
          />
        }
      >
        {screenCanvas}
      </CanvasWorkspace>
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
              ...currentConfigItem.config,
              chartType: currentConfigItem.chartType,
              chartThemeMode: "screen-dark",
            },
          }}
          dataSourceManager={dataSourceManager}
          showChartThemeMode={false}
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
          onConfirm={handleConfirmNewWidgetConfig}
          onClose={() => setPendingConfigItem(null)}
        />
      )}
    </>
  );
});

Screen.displayName = "Screen";

export default Screen;
