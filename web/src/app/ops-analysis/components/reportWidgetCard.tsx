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
import WidgetDataRenderer from '@/app/ops-analysis/components/widgetDataRenderer';
import { WidgetHeaderRuntimeSlotProvider } from '@/app/ops-analysis/components/widgetHeaderRuntimeSlot';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { FilterValue, UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { ReportSection } from '@/app/ops-analysis/types/report';
import type { DashboardWidgetRenderStatus } from '@/app/ops-analysis/renderContract';
import { useTranslation } from '@/utils/i18n';

const REPORT_WIDGET_HEIGHT = 420;

interface ReportWidgetCardProps {
  section: ReportSection;
  index: number;
  reportId?: string | number;
  unifiedFilterValues: Record<string, FilterValue>;
  filterDefinitions: UnifiedFilterDefinition[];
  filterSearchVersion: number;
  dataSource?: DatasourceItem;
  editing: boolean;
  onEdit: (sectionId: string) => void;
  onDelete: (sectionId: string) => void;
}

const ReportWidgetCard: React.FC<ReportWidgetCardProps> = ({
  section,
  index,
  reportId,
  unifiedFilterValues,
  filterDefinitions,
  filterSearchVersion,
  dataSource,
  editing,
  onEdit,
  onDelete,
}) => {
  const { t } = useTranslation();
  const cardRef = useRef<HTMLDivElement | null>(null);
  const [runtimeActive, setRuntimeActive] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [renderStatus, setRenderStatus] = useState<DashboardWidgetRenderStatus>('loading');
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id: section.id, disabled: !editing });

  useEffect(() => {
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
  }, []);

  const setRefs = (element: HTMLDivElement | null) => {
    cardRef.current = element;
    setNodeRef(element);
  };

  return (
    <div
      ref={setRefs}
      style={{
        height: REPORT_WIDGET_HEIGHT,
        transform: CSS.Transform.toString(transform),
        transition,
      }}
      className="flex w-full min-w-0 flex-col overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-3"
    >
      <WidgetHeaderRuntimeSlotProvider>
        {(runtimeSlotRef) => (
          <>
            <div className="mb-2 flex min-h-8 items-start gap-2">
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
                <h3 className="m-0 truncate text-sm font-medium text-[var(--color-text-1)]">
                  {section.valueConfig.name || t('opsAnalysis.report.unnamedComponent')}
                </h3>
                {section.valueConfig.description?.trim() && (
                  <p className="mt-0.5 mb-0 truncate text-xs text-[var(--color-text-3)]">
                    {section.valueConfig.description}
                  </p>
                )}
              </div>
              <div ref={runtimeSlotRef} className="ml-auto max-w-[55%] shrink-0 overflow-x-auto" />
              {renderStatus === 'failed' && (
                <Tooltip title={t('common.retry')}>
                  <Button
                    type="text"
                    size="small"
                    aria-label={t('common.retry')}
                    danger
                    icon={<ReloadOutlined aria-hidden="true" />}
                    onClick={() => setReloadVersion((value) => value + 1)}
                  />
                </Tooltip>
              )}
              {editing && (
                <MoreActionsDropdown
                  items={[
                    {
                      key: 'edit',
                      label: t('common.edit'),
                      onClick: () => onEdit(section.id),
                    },
                    {
                      key: 'delete',
                      label: t('common.delete'),
                      danger: true,
                      onClick: () => onDelete(section.id),
                    },
                  ]}
                />
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-hidden">
              <WidgetDataRenderer
                dashboardId={reportId}
                widgetId={section.id}
                chartType={section.valueConfig.chartType}
                config={section.valueConfig}
                dataSource={dataSource}
                unifiedFilterValues={unifiedFilterValues}
                filterDefinitions={filterDefinitions}
                filterSearchVersion={filterSearchVersion}
                reloadVersion={String(reloadVersion)}
                refreshCause="manual"
                runtimeActive={runtimeActive}
                runtimePriority={{ cause: 1, visibility: 0, distance: 0, order: index }}
                onRenderStatus={(result) => setRenderStatus(result.status)}
              />
            </div>
          </>
        )}
      </WidgetHeaderRuntimeSlotProvider>
    </div>
  );
};

export default ReportWidgetCard;
