'use client';

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { Button, Empty, Modal, Tooltip, message } from 'antd';
import { EditOutlined, PlusOutlined, SettingOutlined } from '@ant-design/icons';
import { closestCenter, DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';

import PermissionWrapper from '@/components/permission';
import { HandledRequestError } from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { useReportApi } from '@/app/ops-analysis/api/report';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
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
import { buildResetFilterValues, syncFilterValuesWithDefinitions } from '@/app/ops-analysis/utils/unifiedFilterState';
import {
  getOpsChartTheme,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import ComponentSelector from '@/app/ops-analysis/components/widgetSelector';
import ViewConfig from '@/app/ops-analysis/components/widgetConfig';
import ReportWidgetCard from '@/app/ops-analysis/components/reportWidgetCard';
import { UnifiedFilterBar, UnifiedFilterConfigModal } from '@/app/ops-analysis/components/unifiedFilter';
import { DashboardRuntimeSchedulerProvider } from '@/app/ops-analysis/context/dashboardRuntimeScheduler';
import ViewWorkspace from '../components/viewWorkspace';

export interface ReportRef {
  hasUnsavedChanges: () => boolean;
}

const createSectionId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `report-widget-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const Report = forwardRef<ReportRef, ReportProps>(({ selectedReport }, ref) => {
  const { t } = useTranslation();
  const { getReportDetail, saveReportViewSets } = useReportApi();
  const dataSourceManager = useDataSourceManager();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [savedViewSets, setSavedViewSets] = useState<ReportViewSets>(EMPTY_REPORT_VIEW_SETS);
  const [draftViewSets, setDraftViewSets] = useState<ReportViewSets>(EMPTY_REPORT_VIEW_SETS);
  const [savedVersion, setSavedVersion] = useState('');
  const [filterValues, setFilterValues] = useState<Record<string, FilterValue>>({});
  const [appliedFilterValues, setAppliedFilterValues] = useState<Record<string, FilterValue>>({});
  const [appliedFilterDefinitions, setAppliedFilterDefinitions] = useState<UnifiedFilterDefinition[]>([]);
  const [filterSearchVersion, setFilterSearchVersion] = useState(0);
  const [filterConfigOpen, setFilterConfigOpen] = useState(false);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [configItem, setConfigItem] = useState<LayoutItem>();
  const [editingSectionId, setEditingSectionId] = useState<string>();
  const [addingComponent, setAddingComponent] = useState(false);
  const loadGuardRef = useRef(createReportLoadGuard());
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const chartTheme = getOpsChartTheme(resolveOpsChartThemeName());

  const dirty = editing && isReportDraftDirty(savedViewSets, draftViewSets);
  useImperativeHandle(ref, () => ({ hasUnsavedChanges: () => dirty }), [dirty]);

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
      setFilterValues({});
      setAppliedFilterValues({});
      setAppliedFilterDefinitions([]);
      return;
    }

    setLoading(true);
    try {
      const detail = await getReportDetail(reportId);
      if (!isCurrentReportLoad(loadGuardRef.current, requestId)) return;
      const normalized = normalizeReportViewSets(detail.view_sets);
      setSavedViewSets(normalized);
      setDraftViewSets(normalized);
      setSavedVersion(detail.updated_at);
      const initialFilterValues = buildResetFilterValues(normalized.filters);
      setFilterValues(initialFilterValues);
      setAppliedFilterValues(initialFilterValues);
      setAppliedFilterDefinitions(normalized.filters);
      const dataSourceIds = normalized.sections
        .map((section) => section.valueConfig.dataSource)
        .filter((id): id is string | number => id !== undefined);
      await loadCanvasDataSources(dataSourceIds);
    } catch (error) {
      if (!isCurrentReportLoad(loadGuardRef.current, requestId)) return;
      console.error('Failed to load report:', error);
      message.error(t('opsAnalysis.report.loadFailed'));
      setEditing(false);
      setSavedViewSets(EMPTY_REPORT_VIEW_SETS);
      setDraftViewSets(EMPTY_REPORT_VIEW_SETS);
      setSavedVersion('');
      setFilterValues({});
      setAppliedFilterValues({});
      setAppliedFilterDefinitions([]);
    } finally {
      if (isCurrentReportLoad(loadGuardRef.current, requestId)) {
        setLoading(false);
      }
    }
  }, [getReportDetail, loadCanvasDataSources, selectedReport?.data_id, t]);

  useEffect(() => {
    setEditing(false);
    setSelectorOpen(false);
    setConfigOpen(false);
    setFilterConfigOpen(false);
    setEditingSectionId(undefined);
    setAddingComponent(false);
    void loadReport();
    return () => {
      invalidateReportLoads(loadGuardRef.current);
    };
  }, [loadReport]);

  const visibleViewSets = editing ? draftViewSets : savedViewSets;
  const canEnterEdit = canEnterReportEdit({
    reportId: selectedReport?.data_id,
    isBuiltIn: selectedReport?.is_build_in,
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
    setDraftViewSets((previous) => ({ ...previous, filters: definitions }));
    setFilterValues((previous) => syncFilterValuesWithDefinitions(definitions, previous));
    setFilterConfigOpen(false);
  };

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

  const toolbar = (
    <div className="flex items-center gap-1.5">
      {editing && (
        <>
          <PermissionWrapper requiredPermissions={['EditChart']}>
            <Tooltip title={t('dashboard.configUnifiedFilterFields')}>
              <Button
                type="text"
                icon={<SettingOutlined style={{ fontSize: 16 }} />}
                aria-label={t('dashboard.configUnifiedFilterFields')}
                onClick={() => setFilterConfigOpen(true)}
                className="rounded-full!"
              />
            </Tooltip>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['EditChart']}>
            <Button
              type="default"
              icon={<PlusOutlined aria-hidden="true" />}
              onClick={() => setSelectorOpen(true)}
              className="rounded-full!"
              style={{
                borderColor: chartTheme.panelBorderColor,
                color: 'var(--color-text-1)',
                background: chartTheme.panelBg,
              }}
            >
              {t('opsAnalysis.report.addComponent')}
            </Button>
          </PermissionWrapper>
        </>
      )}
      <PermissionWrapper requiredPermissions={['EditChart']}>
        {!editing ? (
          <Tooltip title={t('common.edit')}>
            <Button
              type="text"
              aria-label={t('common.edit')}
              icon={<EditOutlined aria-hidden="true" style={{ fontSize: 16 }} />}
              disabled={!canEnterEdit}
              onClick={enterEditMode}
              className="rounded-full!"
            />
          </Tooltip>
        ) : (
          <div className="flex items-center gap-2 ml-4">
            <Button
              disabled={!selectedReport?.data_id}
              onClick={cancelEdit}
              className="rounded-full!"
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="primary"
              loading={saving}
              disabled={!selectedReport?.data_id}
              onClick={save}
              className="rounded-full!"
            >
              {t('common.save')}
            </Button>
          </div>
        )}
      </PermissionWrapper>
    </div>
  );

  const sectionIds = useMemo(() => visibleViewSets.sections.map((section) => section.id), [visibleViewSets.sections]);
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
    />
  ) : null;

  return (
    <ViewWorkspace
      selectedItem={selectedReport}
      loading={loading}
      titleFallback={t('opsAnalysis.report.title')}
      emptyDescription={t('opsAnalysis.report.selectFirst')}
      toolbar={toolbar}
      filterBar={filterBar}
      contentClassName="bg-[var(--color-bg-2)]"
    >
      <div className="h-full overflow-y-auto px-4 pb-4">
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
                      dataSource={dataSourceManager.findDataSource(section.valueConfig.dataSource)}
                      editing={editing}
                      onEdit={editComponent}
                      onDelete={deleteComponent}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          </DashboardRuntimeSchedulerProvider>
        )}
      </div>

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
    </ViewWorkspace>
  );
});

Report.displayName = 'Report';

export default Report;
