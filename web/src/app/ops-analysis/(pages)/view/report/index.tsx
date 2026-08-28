'use client';

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { Button, Empty, Modal, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { closestCenter, DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';

import { HandledRequestError } from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import useBtnPermissions from '@/hooks/usePermissions';
import { useReportApi } from '@/app/ops-analysis/api/report';
import { useDirectoryApi } from '@/app/ops-analysis/api';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useCanvasPeriodicRefresh } from '@/app/ops-analysis/hooks/useCanvasPeriodicRefresh';
import { useCanvasShareAction } from '@/app/ops-analysis/hooks/useCanvasShareAction';
import type { ComponentSelectorConfigItem, FilterValue, LayoutItem, UnifiedFilterDefinition, WidgetConfig } from '@/app/ops-analysis/types/dashBoard';
import type { ReportProps, ReportViewSets } from '@/app/ops-analysis/types/report';
import {
  EMPTY_REPORT_VIEW_SETS,
  appendReportSection,
  beginReportLoad,
  canEnterReportEdit,
  createReportLoadGuard,
  invalidateReportLoads,
  isReportDraftDirty,
  isCurrentReportLoad,
  normalizeReportViewSets,
  removeReportSection,
  reorderReportSection,
  syncReportFiltersFromSections,
  updateReportSection,
} from '@/app/ops-analysis/utils/reportBuilder';
import { copyReportSection } from '@/app/ops-analysis/utils/widgetCopy';
import {
  buildFilterConfigConfirmSnapshot,
  buildResetFilterValues,
  syncFilterValuesWithDefinitions,
} from '@/app/ops-analysis/utils/unifiedFilterState';
import {
  canPersistCanvasRefreshInterval,
  normalizeCanvasRefreshInterval,
} from '@/app/ops-analysis/utils/canvasRefreshInterval';
import type { CanvasRuntimeRefreshCause } from '@/app/ops-analysis/utils/canvasRefreshTimer';
import { exportDashboardToPdf } from '@/app/ops-analysis/utils/exportPdf';
import { prepareReportPrintLayout } from '@/app/ops-analysis/utils/prepareDashboardPrintLayout';
import {
  getOpsChartTheme,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import {
  buildDashboardRenderSignal,
  emitDashboardRenderSignal,
  type DashboardRenderSignal,
  type DashboardWidgetRenderResult,
} from '@/app/ops-analysis/renderContract';
import ComponentSelector from '@/app/ops-analysis/components/widgetSelector';
import ViewConfig from '@/app/ops-analysis/components/widgetConfig';
import ReportWidgetCard from '@/app/ops-analysis/components/reportWidgetCard';
import DashboardSubscriptionModal from '@/app/ops-analysis/components/dashboardSubscriptionModal';
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '@/app/ops-analysis/components/appFullscreen';
import { UnifiedFilterBar, UnifiedFilterConfigModal } from '@/app/ops-analysis/components/unifiedFilter';
import { DashboardRuntimeSchedulerProvider } from '@/app/ops-analysis/context/dashboardRuntimeScheduler';
import ViewWorkspace from '../components/viewWorkspace';
import ReportToolbar from './components/reportToolbar';
import { useCanvasDraft } from '@/app/ops-analysis/hooks/useCanvasDraft';
import {
  restoreDraftRefreshInterval,
  toCanvasDraftResourceId,
  type CanvasDraftPayload,
} from '@/app/ops-analysis/api/canvasDraft';
import { bindCanvasDraftControls } from '@/app/ops-analysis/components/canvasDraftControls';

export interface ReportRef {
  hasUnsavedChanges: () => boolean;
}

const createSectionId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `report-widget-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const waitForReportWidgetsReady = (
  widgetIds: string[],
  resultsRef: { current: Map<string, DashboardWidgetRenderResult> },
  timeoutMs = 60000,
) =>
  new Promise<void>((resolve, reject) => {
    if (widgetIds.length === 0) {
      resolve();
      return;
    }
    const started = Date.now();
    const tick = () => {
      const allSettled = widgetIds.every((widgetId) => {
        const status = resultsRef.current.get(widgetId)?.status;
        return status === 'ready' || status === 'empty' || status === 'failed';
      });
      if (allSettled) {
        resolve();
        return;
      }
      if (Date.now() - started >= timeoutMs) {
        reject(new Error('Report PDF export preparation timed out'));
        return;
      }
      window.setTimeout(tick, 100);
    };
    tick();
  });

const Report = forwardRef<ReportRef, ReportProps>(({
  selectedReport,
  shareMode = false,
  renderMode = false,
  renderFilterValues,
  renderDataSourceIds,
  getReportDetailOverride,
}, ref) => {
  const { t } = useTranslation();
  const { getReportDetail, saveReportViewSets } = useReportApi();
  const { updateItem } = useDirectoryApi();
  const { hasPermission } = useBtnPermissions();
  const dataSourceManager = useDataSourceManager();
  const { shareLoading, openShare } = useCanvasShareAction('report');
  const { isFullscreen, enterFullscreen, exitFullscreen } = useAppViewFullscreen();
  const resumeEditModeAfterFullscreenRef = useRef(false);
  const getReportDetailRef = useRef(getReportDetailOverride ?? getReportDetail);
  const exportRef = useRef<HTMLDivElement | null>(null);
  const renderResultsRef = useRef<Map<string, DashboardWidgetRenderResult>>(new Map());
  const pdfExportResultsRef = useRef<Map<string, DashboardWidgetRenderResult>>(new Map());
  const pdfExportPreparingRef = useRef(false);
  const emittedRenderSignalRef = useRef(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [pdfExportPreparing, setPdfExportPreparing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [savedViewSets, setSavedViewSets] = useState<ReportViewSets>(EMPTY_REPORT_VIEW_SETS);
  const [draftViewSets, setDraftViewSets] = useState<ReportViewSets>(EMPTY_REPORT_VIEW_SETS);
  const [savedVersion, setSavedVersion] = useState('');
  const [savedRefreshInterval, setSavedRefreshInterval] = useState(0);
  const [refreshCause, setRefreshCause] = useState<CanvasRuntimeRefreshCause>('initial');
  const [filterValues, setFilterValues] = useState<Record<string, FilterValue>>({});
  const [appliedFilterValues, setAppliedFilterValues] = useState<Record<string, FilterValue>>({});
  const [appliedFilterDefinitions, setAppliedFilterDefinitions] = useState<UnifiedFilterDefinition[]>([]);
  const [filterSearchVersion, setFilterSearchVersion] = useState(0);
  const [widgetReloadVersion, setWidgetReloadVersion] = useState(0);
  const [filterConfigOpen, setFilterConfigOpen] = useState(false);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [configItem, setConfigItem] = useState<LayoutItem>();
  const [editingSectionId, setEditingSectionId] = useState<string>();
  const [addingComponent, setAddingComponent] = useState(false);
  const [subscriptionModalVisible, setSubscriptionModalVisible] = useState(false);
  const loadGuardRef = useRef(createReportLoadGuard());
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const themeName = renderMode ? 'light' : resolveOpsChartThemeName();
  const chartTheme = getOpsChartTheme(themeName);

  const reportDraftResourceId = toCanvasDraftResourceId(selectedReport?.data_id);
  const getReportDraftPayload = useCallback(
    (): CanvasDraftPayload => ({
      name: selectedReport?.name,
      desc: selectedReport?.desc,
      view_sets: draftViewSets,
      refresh_interval: savedRefreshInterval,
    }),
    [draftViewSets, savedRefreshInterval, selectedReport?.desc, selectedReport?.name],
  );
  const applyReportDraftPayload = useCallback(
    (payload: CanvasDraftPayload) => {
      restoreDraftRefreshInterval(payload, setSavedRefreshInterval);
      const normalized = normalizeReportViewSets(payload.view_sets);
      setDraftViewSets(normalized);
      const nextFilterValues = syncFilterValuesWithDefinitions(
        normalized.filters,
        filterValues,
      );
      setFilterValues(nextFilterValues);
      setAppliedFilterValues(nextFilterValues);
      setAppliedFilterDefinitions(normalized.filters);
    },
    [filterValues, setSavedRefreshInterval],
  );
  const reportDraft = useCanvasDraft({
    resourceType: 'report',
    resourceId: reportDraftResourceId,
    enabled: Boolean(
      editing &&
        !shareMode &&
        !renderMode &&
        reportDraftResourceId &&
        !selectedReport?.is_build_in,
    ),
    getPayload: getReportDraftPayload,
    applyPayload: applyReportDraftPayload,
  });

  const dirty = editing && isReportDraftDirty(savedViewSets, draftViewSets);
  useImperativeHandle(ref, () => ({ hasUnsavedChanges: () => dirty }), [dirty]);

  useEffect(() => {
    getReportDetailRef.current = getReportDetailOverride ?? getReportDetail;
  }, [getReportDetail, getReportDetailOverride]);

  useEffect(() => {
    if (!dirty) return undefined;
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [dirty]);

  const loadCanvasDataSources = dataSourceManager.loadCanvasDataSources;
  const loadReport = useCallback(async () => {
    const requestId = beginReportLoad(loadGuardRef.current);
    const reportId = selectedReport?.data_id;
    if (!reportId) {
      setSavedViewSets(EMPTY_REPORT_VIEW_SETS);
      setDraftViewSets(EMPTY_REPORT_VIEW_SETS);
      setSavedVersion('');
      setSavedRefreshInterval(0);
      setFilterValues({});
      setAppliedFilterValues({});
      setAppliedFilterDefinitions([]);
      return;
    }

    setLoading(true);
    try {
      const detail = await getReportDetailRef.current(reportId);
      if (!isCurrentReportLoad(loadGuardRef.current, requestId)) return;
      const normalized = normalizeReportViewSets(detail.view_sets);
      setSavedViewSets(normalized);
      setDraftViewSets(normalized);
      setSavedVersion(detail.updated_at || '');
      setSavedRefreshInterval(normalizeCanvasRefreshInterval(detail.refresh_interval));
      const initialFilterValues = renderMode
        ? syncFilterValuesWithDefinitions(normalized.filters, renderFilterValues ?? {})
        : buildResetFilterValues(normalized.filters);
      setFilterValues(initialFilterValues);
      setAppliedFilterValues(initialFilterValues);
      setAppliedFilterDefinitions(normalized.filters);
      const dataSourceIds = Array.from(new Set([
        ...normalized.sections
          .map((section) => section.valueConfig.dataSource)
          .filter((id): id is string | number => id !== undefined),
        ...(renderDataSourceIds || []),
      ]));
      await loadCanvasDataSources(dataSourceIds);
    } catch (error) {
      if (!isCurrentReportLoad(loadGuardRef.current, requestId)) return;
      console.error('Failed to load report:', error);
      if (!renderMode) {
        message.error(t('opsAnalysis.report.loadFailed'));
      }
      setEditing(false);
      setSavedViewSets(EMPTY_REPORT_VIEW_SETS);
      setDraftViewSets(EMPTY_REPORT_VIEW_SETS);
      setSavedVersion('');
      setSavedRefreshInterval(0);
      setFilterValues({});
      setAppliedFilterValues({});
      setAppliedFilterDefinitions([]);
      if (renderMode && !emittedRenderSignalRef.current) {
        emittedRenderSignalRef.current = true;
        emitDashboardRenderSignal({
          type: 'report-failed',
          dashboardId: String(selectedReport?.data_id),
          widgets: [],
          error: error instanceof Error ? error.message : 'Report layout load failed',
        });
      }
    } finally {
      if (isCurrentReportLoad(loadGuardRef.current, requestId)) {
        setLoading(false);
      }
    }
  }, [loadCanvasDataSources, renderDataSourceIds, renderFilterValues, renderMode, selectedReport?.data_id, t]);

  useEffect(() => {
    setEditing(false);
    setSelectorOpen(false);
    setConfigOpen(false);
    setFilterConfigOpen(false);
    setEditingSectionId(undefined);
    setAddingComponent(false);
    setSubscriptionModalVisible(false);
    setWidgetReloadVersion(0);
    setFilterSearchVersion(0);
    setRefreshCause('initial');
    renderResultsRef.current = new Map();
    emittedRenderSignalRef.current = false;
    void loadReport();
    return () => {
      invalidateReportLoads(loadGuardRef.current);
    };
  }, [loadReport]);

  const visibleViewSets = editing ? draftViewSets : savedViewSets;
  const canEnterEdit = canEnterReportEdit({
    reportId: selectedReport?.data_id,
    isBuiltIn: Boolean(selectedReport?.is_build_in) || shareMode || renderMode,
    savedVersion,
    loading,
  });

  const handleFilterSearch = (values: Record<string, FilterValue>) => {
    setFilterValues(values);
    setAppliedFilterValues(values);
    setAppliedFilterDefinitions(visibleViewSets.filters);
    setFilterSearchVersion((previous) => previous + 1);
  };

  const handleFilterConfigConfirm = (definitions: UnifiedFilterDefinition[]) => {
    const snapshot = buildFilterConfigConfirmSnapshot(
      definitions,
      filterValues,
      appliedFilterValues,
    );
    setDraftViewSets((previous) => ({ ...previous, filters: snapshot.definitions }));
    setAppliedFilterDefinitions(snapshot.definitions);
    setFilterValues(snapshot.filterValues);
    setAppliedFilterValues(snapshot.appliedFilterValues);
    setFilterConfigOpen(false);
  };

  const handleRefresh = useCallback(() => {
    setRefreshCause('manual');
    setWidgetReloadVersion((previous) => previous + 1);
  }, []);

  const handlePeriodicRefresh = useCallback(
    (cause: CanvasRuntimeRefreshCause = 'periodic') => {
      setRefreshCause(cause);
      setWidgetReloadVersion((previous) => previous + 1);
    },
    [],
  );

  const canPersistRefreshInterval = canPersistCanvasRefreshInterval({
    shareMode,
    isBuiltIn: Boolean(selectedReport?.is_build_in),
    hasEditPermission: hasPermission(['EditChart']),
  });

  const { effectiveRefreshInterval, handleFrequencyChange } =
    useCanvasPeriodicRefresh({
      canvasId: selectedReport?.data_id,
      savedInterval: savedRefreshInterval,
      canPersist: canPersistRefreshInterval,
      enabled: !renderMode && !pdfExportPreparing && !editing,
      patchRefreshInterval: async (interval) => {
        if (!selectedReport?.data_id) {
          return;
        }
        await updateItem('report', selectedReport.data_id, {
          refresh_interval: interval,
        });
      },
      onPeriodicRefresh: handlePeriodicRefresh,
      onSavedIntervalChange: setSavedRefreshInterval,
    });

  const enterEditMode = () => {
    if (!canEnterEdit) return;
    setDraftViewSets(savedViewSets);
    setEditing(true);
  };

  const cancelEdit = () => {
    setDraftViewSets(savedViewSets);
    const restoredValues = syncFilterValuesWithDefinitions(savedViewSets.filters, filterValues);
    setFilterValues(restoredValues);
    setAppliedFilterValues(restoredValues);
    setAppliedFilterDefinitions(savedViewSets.filters);
    setEditing(false);
    setSelectorOpen(false);
    setConfigOpen(false);
    setFilterConfigOpen(false);
  };

  const save = async () => {
    const reportId = selectedReport?.data_id;
    if (!reportId || !savedVersion) return;
    setSaving(true);
    try {
      const detail = await saveReportViewSets(reportId, {
        view_sets: draftViewSets,
        expected_updated_at: savedVersion,
      });
      const normalized = normalizeReportViewSets(detail.view_sets);
      setSavedViewSets(normalized);
      setDraftViewSets(normalized);
      setSavedVersion(detail.updated_at);
      const nextFilterValues = syncFilterValuesWithDefinitions(normalized.filters, filterValues);
      setFilterValues(nextFilterValues);
      setAppliedFilterValues(nextFilterValues);
      setAppliedFilterDefinitions(normalized.filters);
      setEditing(false);
      message.success(t('opsAnalysis.report.saveSuccess'));
    } catch (error) {
      if (error instanceof HandledRequestError && error.status === 409) {
        message.error(t('opsAnalysis.report.versionConflict'));
      } else {
        message.error(t('opsAnalysis.report.saveFailed'));
      }
    } finally {
      setSaving(false);
    }
  };

  const openNewComponentConfig = (item: ComponentSelectorConfigItem) => {
    setSelectorOpen(false);
    setAddingComponent(true);
    setEditingSectionId(undefined);
    setConfigItem({
      i: '', x: 0, y: 0, w: 12, h: 4,
      name: item.name,
      description: item.desc,
      valueConfig: { dataSource: item.dataSource, chartType: item.chartType, dataSourceParams: [] },
    });
    setConfigOpen(true);
  };

  const editComponent = (sectionId: string) => {
    const section = draftViewSets.sections.find((item) => item.id === sectionId);
    if (!section) return;
    setAddingComponent(false);
    setEditingSectionId(sectionId);
    setConfigItem({
      i: sectionId, x: 0, y: 0, w: 12, h: 4,
      name: section.valueConfig.name,
      description: section.valueConfig.description,
      valueConfig: section.valueConfig,
    });
    setConfigOpen(true);
  };

  const confirmComponentConfig = (values: WidgetConfig) => {
    const withSection = addingComponent
      ? appendReportSection(draftViewSets, { id: createSectionId(), valueConfig: values })
      : editingSectionId
        ? updateReportSection(draftViewSets, editingSectionId, values)
        : draftViewSets;
    const synced = syncReportFiltersFromSections(withSection, dataSourceManager.dataSources);
    const nextIds = withSection.sections
      .map((section) => section.valueConfig.dataSource)
      .filter((id): id is string | number => id !== undefined);

    setDraftViewSets(synced);
    setFilterValues((previous) => syncFilterValuesWithDefinitions(synced.filters, previous));

    void loadCanvasDataSources(nextIds).then((loadedDataSources) => {
      setDraftViewSets((previous) => {
        const next = syncReportFiltersFromSections(previous, loadedDataSources);
        setFilterValues((current) => syncFilterValuesWithDefinitions(next.filters, current));
        return next;
      });
    });
    setConfigOpen(false);
    setConfigItem(undefined);
    setEditingSectionId(undefined);
    setAddingComponent(false);
  };

  const copyComponent = (sectionId: string) => {
    const withCopy = copyReportSection(draftViewSets, sectionId, {
      createId: createSectionId,
    });
    if (withCopy === draftViewSets) return;
    const synced = syncReportFiltersFromSections(withCopy, dataSourceManager.dataSources);
    const nextIds = withCopy.sections
      .map((section) => section.valueConfig.dataSource)
      .filter((id): id is string | number => id !== undefined);

    setDraftViewSets(synced);
    setFilterValues((previous) => syncFilterValuesWithDefinitions(synced.filters, previous));

    void loadCanvasDataSources(nextIds).then((loadedDataSources) => {
      setDraftViewSets((previous) => {
        const next = syncReportFiltersFromSections(previous, loadedDataSources);
        setFilterValues((current) => syncFilterValuesWithDefinitions(next.filters, current));
        return next;
      });
    });
  };

  const deleteComponent = (sectionId: string) => {
    Modal.confirm({
      title: t('opsAnalysis.report.deleteComponentTitle'),
      content: t('opsAnalysis.report.deleteComponentContent'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk: () => {
        const next = syncReportFiltersFromSections(
          removeReportSection(draftViewSets, sectionId),
          dataSourceManager.dataSources,
        );
        setDraftViewSets(next);
        setFilterValues((previous) => syncFilterValuesWithDefinitions(next.filters, previous));
      },
    });
  };

  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    setDraftViewSets((previous) => {
      return reorderReportSection(previous, String(active.id), String(over.id));
    });
  };

  useEffect(() => {
    if (isFullscreen || !resumeEditModeAfterFullscreenRef.current) {
      return;
    }
    resumeEditModeAfterFullscreenRef.current = false;
    setEditing(true);
  }, [isFullscreen]);

  const handleFullscreenToggle = useCallback(() => {
    if (isFullscreen) {
      exitFullscreen();
      return;
    }
    resumeEditModeAfterFullscreenRef.current = editing;
    if (editing) {
      setEditing(false);
    }
    enterFullscreen();
  }, [editing, enterFullscreen, exitFullscreen, isFullscreen]);

  const sectionIds = useMemo(
    () => visibleViewSets.sections.map((section) => section.id),
    [visibleViewSets.sections],
  );

  const handleExportPdf = useCallback(async () => {
    if (!exportRef.current || exporting) return;
    setExporting(true);
    pdfExportResultsRef.current = new Map();
    pdfExportPreparingRef.current = true;
    setPdfExportPreparing(true);
    try {
      await waitForReportWidgetsReady(sectionIds, pdfExportResultsRef);
      await exportDashboardToPdf(
        exportRef.current,
        selectedReport?.name || 'report',
      );
      message.success(t('dashboard.exportPdfSuccess'));
    } catch (error) {
      console.error('Failed to export report PDF:', error);
      message.error(t('dashboard.exportPdfFailed'));
    } finally {
      pdfExportPreparingRef.current = false;
      setPdfExportPreparing(false);
      setExporting(false);
    }
  }, [exporting, sectionIds, selectedReport?.name, t]);

  const emitPreparedRenderSignal = useCallback(
    async (signal: DashboardRenderSignal) => {
      if (emittedRenderSignalRef.current) return;
      emittedRenderSignalRef.current = true;
      if (signal.type === 'report-ready') {
        try {
          await prepareReportPrintLayout();
        } catch (error) {
          emitDashboardRenderSignal({
            type: 'report-failed',
            dashboardId: signal.dashboardId,
            widgets: signal.widgets,
            error:
              error instanceof Error
                ? error.message
                : 'Report print preparation failed',
          });
          return;
        }
      }
      emitDashboardRenderSignal(signal);
    },
    [],
  );

  const handleWidgetRenderStatus = useCallback(
    (result: DashboardWidgetRenderResult) => {
      if (pdfExportPreparingRef.current) {
        pdfExportResultsRef.current.set(result.widgetId, result);
      }
      if (!renderMode || emittedRenderSignalRef.current) return;
      renderResultsRef.current.set(result.widgetId, result);
      const signal = buildDashboardRenderSignal(
        selectedReport?.data_id || 'unknown',
        sectionIds,
        renderResultsRef.current,
      );
      if (signal) {
        void emitPreparedRenderSignal(signal);
      }
    },
    [emitPreparedRenderSignal, renderMode, sectionIds, selectedReport?.data_id],
  );

  useEffect(() => {
    if (!renderMode || emittedRenderSignalRef.current || loading) return;
    if (sectionIds.length > 0) return;
    const frame = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        void emitPreparedRenderSignal({
          type: 'report-ready',
          dashboardId: String(selectedReport?.data_id || 'unknown'),
          widgets: [],
        });
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [emitPreparedRenderSignal, loading, renderMode, sectionIds.length, selectedReport?.data_id]);

  const filterLayoutItems = useMemo<LayoutItem[]>(
    () => draftViewSets.sections.map((section, index) => ({
      i: section.id,
      x: 0,
      y: index,
      w: 12,
      h: 4,
      name: section.valueConfig.name,
      valueConfig: section.valueConfig,
    })),
    [draftViewSets.sections],
  );
  const filterBar = visibleViewSets.filters.length > 0 ? (
    <UnifiedFilterBar
      definitions={visibleViewSets.filters}
      values={filterValues}
      onSearch={handleFilterSearch}
      onReset={handleFilterSearch}
      popupZIndex={isFullscreen ? 1200 : undefined}
    />
  ) : null;

  const reportCanvas = (
    <div
      className={renderMode ? 'w-full overflow-visible px-4 pb-4' : 'h-full overflow-y-auto px-4 pb-4'}
      data-export-expand="true"
    >
      {visibleViewSets.sections.length === 0 ? (
        <div className="flex min-h-[360px] items-center justify-center rounded-lg border border-dashed border-[var(--color-border-2)] bg-[var(--color-bg-1)]">
          <Empty description={t('opsAnalysis.report.emptyDescription')}>
            {editing && (
              <Button type="primary" icon={<PlusOutlined aria-hidden="true" />} onClick={() => setSelectorOpen(true)}>
                {t('opsAnalysis.report.addComponent')}
              </Button>
            )}
          </Empty>
        </div>
      ) : (
        <DashboardRuntimeSchedulerProvider>
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={sectionIds} strategy={verticalListSortingStrategy}>
              <div className="flex flex-col gap-3">
                {visibleViewSets.sections.map((section, index) => (
                  <ReportWidgetCard
                    key={section.id}
                    section={section}
                    index={index}
                    reportId={selectedReport?.data_id}
                    unifiedFilterValues={appliedFilterValues}
                    filterDefinitions={appliedFilterDefinitions}
                    filterSearchVersion={filterSearchVersion}
                    reloadVersion={widgetReloadVersion}
                    refreshCause={refreshCause}
                    dataSource={dataSourceManager.findDataSource(section.valueConfig.dataSource)}
                    editing={editing}
                    eagerRuntime={renderMode || pdfExportPreparing}
                    onEdit={editComponent}
                    onCopy={copyComponent}
                    onDelete={deleteComponent}
                    onWidgetRenderStatus={handleWidgetRenderStatus}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        </DashboardRuntimeSchedulerProvider>
      )}
    </div>
  );

  const toolbar = renderMode ? null : (
    <ReportToolbar
      selectedReport={selectedReport}
      chartTheme={chartTheme}
      exporting={exporting}
      isFullscreen={isFullscreen}
      editing={editing}
      saving={saving}
      canEnterEdit={canEnterEdit}
      onRefresh={handleRefresh}
      frequenceValue={effectiveRefreshInterval}
      onFrequencyChange={handleFrequencyChange}
      onToggleFullscreen={handleFullscreenToggle}
      onExportPdf={handleExportPdf}
      onOpenFilterConfig={() => setFilterConfigOpen(true)}
      onOpenAddComponent={() => setSelectorOpen(true)}
      onToggleEditMode={enterEditMode}
      onCancelEdit={cancelEdit}
      onSave={save}
      editExtra={bindCanvasDraftControls(reportDraft)}
      shareMode={shareMode}
      shareLoading={shareLoading}
      onOpenShare={!shareMode && selectedReport?.data_id ? () => { void openShare(selectedReport.data_id); } : undefined}
      onOpenSubscriptions={
        !shareMode && selectedReport?.data_id
          ? () => setSubscriptionModalVisible(true)
          : undefined
      }
    />
  );

  const workspace = (
    <>
      {renderMode ? (
        <div
          className="w-full min-h-screen overflow-visible bg-[var(--color-bg-2)] p-4"
          data-dashboard-render-root="true"
        >
          {reportCanvas}
        </div>
      ) : isFullscreen ? (
        <div
          ref={exportRef}
          className="flex min-h-0 flex-1 flex-col"
          data-export-expand="true"
        >
          {filterBar && (
            <div className="shrink-0 bg-[var(--color-bg-1)] px-2.5 pb-2 pt-1">
              {filterBar}
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-hidden pt-1" data-export-expand="true">
            {reportCanvas}
          </div>
        </div>
      ) : (
        <ViewWorkspace
          selectedItem={selectedReport}
          loading={loading}
          titleFallback={t('opsAnalysis.report.title')}
          emptyDescription={t('opsAnalysis.report.selectFirst')}
          toolbar={toolbar}
          filterBar={filterBar}
          contentRef={exportRef}
          contentClassName="bg-[var(--color-bg-2)]"
        >
          {reportCanvas}
        </ViewWorkspace>
      )}
    </>
  );

  return (
    <div
      className={`flex flex-col ${
        isFullscreen
          ? 'fixed inset-0 h-screen w-screen overflow-hidden'
          : renderMode
            ? 'w-full min-h-screen overflow-visible'
            : 'h-full flex-1 overflow-auto'
      }`}
      style={{
        backgroundColor: 'var(--color-bg-2)',
        zIndex: isFullscreen ? 1100 : undefined,
      }}
    >
      <AppViewFullscreenExit visible={isFullscreen} onExit={exitFullscreen} />
      {workspace}

      <ComponentSelector
        visible={selectorOpen}
        surface="report"
        onCancel={() => setSelectorOpen(false)}
        onOpenConfig={openNewComponentConfig}
      />
      <ViewConfig
        open={configOpen}
        item={configItem}
        surface="report"
        dataSourceManager={dataSourceManager}
        filterDefinitions={draftViewSets.filters}
        unifiedFilterValues={filterValues}
        onConfirm={confirmComponentConfig}
        onClose={() => {
          setConfigOpen(false);
          setConfigItem(undefined);
          setEditingSectionId(undefined);
          setAddingComponent(false);
        }}
      />
      <UnifiedFilterConfigModal
        open={filterConfigOpen}
        onCancel={() => setFilterConfigOpen(false)}
        onConfirm={handleFilterConfigConfirm}
        definitions={draftViewSets.filters}
        layoutItems={filterLayoutItems}
        dataSources={dataSourceManager.dataSources}
      />
      {selectedReport?.data_id != null && (
        <DashboardSubscriptionModal
          open={subscriptionModalVisible}
          resourceType="report"
          resourceId={Number(selectedReport.data_id)}
          appliedFilterValues={appliedFilterValues}
          onClose={() => setSubscriptionModalVisible(false)}
        />
      )}
    </div>
  );
});

Report.displayName = 'Report';

export default Report;
