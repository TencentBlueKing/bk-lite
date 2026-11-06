'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Modal, Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import useBtnPermissions from '@/hooks/usePermissions';
import { useTranslation } from '@/utils/i18n';
import { useCarouselApi } from '@/app/ops-analysis/api/carousel';
import type { CarouselSummary } from '@/app/ops-analysis/types/carousel';
import { carouselDurationMessage } from '@/app/ops-analysis/utils/carouselDraft';

interface CarouselListProps {
  keyword: string;
  refreshKey: number;
  selectedId?: string | null;
  onSelect: (id: string) => void;
  onAutoSelect?: (id: string) => void;
  onEditBasic: (carousel: CarouselSummary) => void;
  hasUnsavedCarouselChanges?: () => boolean;
  onDeleted: (id: number) => void;
}

const CarouselList: React.FC<CarouselListProps> = ({
  keyword,
  refreshKey,
  selectedId,
  onSelect,
  onAutoSelect,
  onEditBasic,
  hasUnsavedCarouselChanges,
  onDeleted,
}) => {
  const { t } = useTranslation();
  const { hasPermission } = useBtnPermissions();
  const { listCarousels, deleteCarousel } = useCarouselApi();
  const [rows, setRows] = useState<CarouselSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const requestedSelection = useRef<string | null>(null);
  const requestKey = `${refreshKey}|${keyword}`;
  const [trackedRequest, setTrackedRequest] = useState(requestKey);
  if (trackedRequest !== requestKey) {
    setTrackedRequest(requestKey);
    setLoading(true);
  }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listCarousels(keyword.trim() || undefined));
    } catch (error) {
      console.error('Failed to load carousels:', error);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [keyword, listCarousels]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  useEffect(() => {
    if (loading || selectedId) {
      if (selectedId) requestedSelection.current = null;
      return;
    }
    const first = rows[0];
    if (!first) return;
    const id = String(first.id);
    if (requestedSelection.current === id) return;
    requestedSelection.current = id;
    (onAutoSelect ?? onSelect)(id);
  }, [loading, onAutoSelect, onSelect, rows, selectedId]);

  const canEdit = hasPermission(['EditChart']);
  const canDelete = hasPermission(['DeleteChart']);

  return (
    <Spin spinning={loading}>
      {rows.length === 0 ? (
        <CompactEmptyState description={t('opsCarousel.emptyList')} />
      ) : (
        <div className="flex flex-col gap-1">
          {rows.map((row) => {
            const selected = selectedId === String(row.id);
            const playableCount = row.playable_count ?? row.item_count;
            const invalidCount = Math.max(0, row.item_count - playableCount);
            const duration = carouselDurationMessage(
              row.duration_seconds ?? playableCount * row.default_dwell_seconds,
            );
            const subtitle = invalidCount > 0
              ? t('opsCarousel.listSubtitleWithInvalid', undefined, {
                count: playableCount,
                duration: t(duration.id, undefined, duration.values),
                invalid: invalidCount,
              })
              : t('opsCarousel.listSubtitle', undefined, {
                count: playableCount,
                duration: t(duration.id, undefined, duration.values),
              });
            const menuItems = [
              ...(canEdit ? [{
                key: 'edit',
                label: t('opsCarousel.editBasic'),
                onClick: () => onEditBasic(row),
              }] : []),
              ...(canDelete ? [{
                key: 'delete',
                label: t('common.delete'),
                danger: true,
                onClick: () => {
                  const dirty = selectedId === String(row.id) && Boolean(hasUnsavedCarouselChanges?.());
                  Modal.confirm({
                    title: t('opsCarousel.deleteConfirm'),
                    content: dirty
                      ? `${row.name} ${t('opsAnalysisSidebar.unsavedChangesWarning')}`
                      : row.name,
                    okText: t('common.confirm'),
                    cancelText: t('common.cancel'),
                    okButtonProps: { danger: true },
                    centered: true,
                    onOk: () => deleteCarousel(row.id).then(() => onDeleted(row.id)),
                  });
                },
              }] : []),
            ];
            return (
              <div
                key={row.id}
                className={`flex items-center gap-1 rounded px-1 py-1 ${
                  selected ? 'bg-[var(--color-fill-2)]' : 'hover:bg-[var(--color-fill-1)]'
                }`}
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 cursor-pointer bg-transparent text-left"
                  onClick={() => onSelect(String(row.id))}
                >
                  <EllipsisWithTooltip
                    className="block truncate text-sm text-[var(--color-text-1)]"
                    text={row.name}
                  />
                  <span className="text-xs text-[var(--color-text-3)]">{subtitle}</span>
                </button>
                {menuItems.length > 0 && (
                  <MoreActionsDropdown
                    stopPropagation
                    labelAlign="start"
                    items={menuItems}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </Spin>
  );
};

export default CarouselList;
