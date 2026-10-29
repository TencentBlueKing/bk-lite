'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Tooltip } from 'antd';
import {
  HolderOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

import MoreActionsDropdown from '@/components/more-actions-dropdown';
import WidgetCsvHoverButton from '@/app/ops-analysis/components/widgetCsvHoverButton';
import InteractionTitleIcon from '@/app/ops-analysis/components/interactionTitleIcon';
import WidgetDataRenderer from '@/app/ops-analysis/components/widgetDataRenderer';
import { WidgetHeaderRuntimeSlotProvider } from '@/app/ops-analysis/components/widgetHeaderRuntimeSlot';
import { notifyWidgetCsvExportNotStarted, useWidgetCsvExportRegistry } from '@/app/ops-analysis/context/widgetCsvExportRegistry';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { FilterValue, UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { ReportSection } from '@/app/ops-analysis/types/report';
import type {
  DashboardWidgetRenderResult,
  DashboardWidgetRenderStatus,
} from '@/app/ops-analysis/renderContract';
import type { CanvasRuntimeRefreshCause } from '@/app/ops-analysis/utils/canvasRefreshTimer';
import { useFilterTemplateText } from '@/app/ops-analysis/context/filterTemplate';
import { useTranslation } from '@/utils/i18n';
import {
  buildAnalysisWidgetMenuItems,
  buildDashboardWidgetMenuKeys,
  resolveWidgetCsvExportEntry,
} from '@/app/ops-analysis/utils/widgetCsvMenu';

// Canvas and subscription PDF share this height. Do not mark the card
// `data-export-expand`: that unlocks 420px in print while the table body
// still clips, unlike dashboard widgets.
const REPORT_WIDGET_HEIGHT = 420;

interface ReportWidgetCardProps {
  section: ReportSection;
  index: number;
  reportId?: string | number;
  unifiedFilterValues: Record<string, FilterValue>;
  filterDefinitions: UnifiedFilterDefinition[];
  filterSearchVersion: number;
  reloadVersion?: number;
  refreshCause?: CanvasRuntimeRefreshCause;
  dataSource?: DatasourceItem;
  editing: boolean;
  shareMode?: boolean;
  isFullscreen?: boolean;
  renderMode?: boolean;
  pdfExportPreparing?: boolean;
  isBuiltIn?: boolean;
  eagerRuntime?: boolean;
  onEdit: (sectionId: string) => void;
  onCopy?: (sectionId: string) => void;
  onDelete: (sectionId: string) => void;
  onWidgetRenderStatus?: (result: DashboardWidgetRenderResult) => void;
}

const ReportWidgetCard: React.FC<ReportWidgetCardProps> = ({
  section,
  index,
  reportId,
  unifiedFilterValues,
  filterDefinitions,
  filterSearchVersion,
  reloadVersion = 0,
  refreshCause = 'manual',
  dataSource,
  editing,
  shareMode = false,
  isFullscreen = false,
  renderMode = false,
  pdfExportPreparing = false,
  isBuiltIn = false,
  eagerRuntime = false,
  onEdit,
  onCopy,
  onDelete,
  onWidgetRenderStatus,
}) => {
  const { t } = useTranslation();
  const title = useFilterTemplateText(section.valueConfig.name);
  const description = useFilterTemplateText(section.valueConfig.description);
  const csvExportRegistry = useWidgetCsvExportRegistry();
  const cardRef = useRef<HTMLDivElement | null>(null);
  const [runtimeActive, setRuntimeActive] = useState(eagerRuntime);
  const [localReloadVersion, setLocalReloadVersion] = useState(0);
  const [renderStatus, setRenderStatus] = useState<DashboardWidgetRenderStatus>('loading');
  const [exportRawData, setExportRawData] = useState<unknown>(undefined);
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id: section.id, disabled: !editing });

  useEffect(() => {
    if (!eagerRuntime || renderStatus === 'loading') {
      return;
    }
    onWidgetRenderStatus?.({ widgetId: section.id, status: renderStatus });
  }, [eagerRuntime, onWidgetRenderStatus, renderStatus, section.id]);

  useEffect(() => {
    if (eagerRuntime) {
      setRuntimeActive(true);
      return;
    }
    const element = cardRef.current;
    if (!element || typeof IntersectionObserver === 'undefined') {
      setRuntimeActive(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setRuntimeActive(true);
          observer.disconnect();
        }
      },
      { rootMargin: '400px 0px' },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [eagerRuntime]);

  const setRefs = (element: HTMLDivElement | null) => {
    cardRef.current = element;
    setNodeRef(element);
  };

  const exportEntry = resolveWidgetCsvExportEntry({
    surface: 'report',
    chartType: section.valueConfig.chartType,
    editMode: editing,
    shareMode,
    fullscreen: isFullscreen,
    renderMode: renderMode || pdfExportPreparing,
    rawData: exportRawData,
  });
  const menuKeys = buildDashboardWidgetMenuKeys({
    surface: 'report',
    isEditMode: editing,
    shareMode,
    isBuiltIn,
    renderMode: renderMode || pdfExportPreparing,
    fullscreen: isFullscreen,
    chartType: section.valueConfig.chartType,
    sceneWidgetType: section.valueConfig.sceneWidgetType,
    rawData: exportRawData,
  });
  const exportCsv = () => {
    void csvExportRegistry?.run(section.id, {
      title: title || '',
    }).then((started) => {
      notifyWidgetCsvExportNotStarted(started, t);
    });
  };
  const menuItems = buildAnalysisWidgetMenuItems({
    keys: menuKeys,
    t,
    onEdit: () => onEdit(section.id),
    onCopy: () => onCopy?.(section.id),
    onDelete: () => onDelete(section.id),
    onExportCsv: exportCsv,
  });

  return (
    <div
      ref={setRefs}
      style={{
        height: REPORT_WIDGET_HEIGHT,
        transform: CSS.Transform.toString(transform),
        transition,
      }}
      className="group relative flex w-full min-w-0 flex-col overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-3"
    >
      <WidgetHeaderRuntimeSlotProvider>
        {(runtimeSlotRef) => (
          <>
            <div className="mb-2 flex min-h-8 min-w-0 items-start gap-2">
              {editing && (
                <Button
                  type="text"
                  size="small"
                  aria-label={t('opsAnalysis.report.dragComponent')}
                  icon={<HolderOutlined aria-hidden="true" />}
                  className="cursor-grab"
                  {...attributes}
                  {...listeners}
                />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-1">
                  <h3 className="m-0 min-w-0 truncate text-sm font-medium text-[var(--color-text-1)]">
                    {title.trim() ? title : t('opsAnalysis.report.unnamedComponent')}
                  </h3>
                </div>
                {section.valueConfig.description?.trim() && (
                  <p className="mt-0.5 mb-0 truncate text-xs text-[var(--color-text-3)]">
                    {description}
                  </p>
                )}
              </div>
              <div ref={runtimeSlotRef} className="ml-auto min-w-0 max-w-[55%] overflow-x-auto" />
              {renderStatus === 'failed' && (
                <Tooltip title={t('common.retry')}>
                  <Button
                    type="text"
                    size="small"
                    aria-label={t('common.retry')}
                    danger
                    icon={<ReloadOutlined aria-hidden="true" />}
                    onClick={() => setLocalReloadVersion((value) => value + 1)}
                  />
                </Tooltip>
              )}
              {exportEntry === 'hover' && (
                <WidgetCsvHoverButton
                  label={t('dashboard.exportCsv')}
                  onClick={exportCsv}
                />
              )}
              <InteractionTitleIcon config={section.valueConfig} />
              {menuItems.length > 0 && (
                <div data-export-hidden="true">
                  <MoreActionsDropdown
                    trigger={['hover']}
                    labelAlign="start"
                    buttonClassName="cursor-pointer text-(--color-text-2) transition-colors hover:!bg-transparent hover:text-(--color-text-1)"
                    items={menuItems}
                  />
                </div>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <WidgetDataRenderer
                dashboardId={reportId}
                widgetId={section.id}
                surface="report"
                chartType={section.valueConfig.chartType}
                config={section.valueConfig}
                dataSource={dataSource}
                unifiedFilterValues={unifiedFilterValues}
                filterDefinitions={filterDefinitions}
                filterSearchVersion={filterSearchVersion}
                reloadVersion={`${reloadVersion}:${localReloadVersion}`}
                refreshCause={refreshCause}
                runtimeActive={runtimeActive}
                runtimePriority={{ cause: 1, visibility: 0, distance: 0, order: index }}
                onRawData={setExportRawData}
                onRenderStatus={(result) => {
                  setRenderStatus(result.status);
                  onWidgetRenderStatus?.(result);
                }}
              />
            </div>
          </>
        )}
      </WidgetHeaderRuntimeSlotProvider>
    </div>
  );
};

export default ReportWidgetCard;
