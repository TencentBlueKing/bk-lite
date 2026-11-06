'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Empty, Input, Select, Tree, message } from 'antd';
import type { DataNode } from 'antd/lib/tree';
import OperateDrawer from '@/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import {
  CANVAS_TYPE_ORDER,
  getCanvasTypeMeta,
  isCanvasType,
  type CanvasType,
} from '@/app/ops-analysis/constants/canvasTypes';
import type { DirItem } from '@/app/ops-analysis/types';
import { CAROUSEL_MAX_ITEMS } from '@/app/ops-analysis/utils/carouselPlayer';
import {
  canvasIdentityKey,
  mergeCanvasChecks,
  projectedCarouselItemCount,
  remainingCapacity,
  selectionChangeCounts,
  shouldShowRemainingCapacity,
} from '@/app/ops-analysis/utils/carouselDraft';
import { CanvasTypeIcon } from './canvasTypeIcon';

export interface PickedCanvas {
  resourceType: CanvasType;
  canvasId: number;
  name: string;
  groups: number[];
}

interface CanvasPickerProps {
  open: boolean;
  directories: DirItem[];
  selectedKeys: string[];
  currentItems: { resourceType: string; canvasId: number }[];
  loadFailed?: boolean;
  onClose: () => void;
  onConfirm: (canvases: PickedCanvas[], treeKeys: string[]) => void;
}

type TypeFilter = 'all' | CanvasType;

const toGroupIds = (groups?: number[]): number[] =>
  (groups || []).map((groupId) => Number(groupId)).filter((groupId) => Number.isFinite(groupId));

const CanvasPicker: React.FC<CanvasPickerProps> = ({
  open,
  directories,
  selectedKeys,
  currentItems,
  loadFailed = false,
  onClose,
  onConfirm,
}) => {
  const { t } = useTranslation();
  const [keyword, setKeyword] = useState('');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');
  const [checked, setChecked] = useState<string[]>([]);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (open && !wasOpen.current) {
      setKeyword('');
      setTypeFilter('all');
      setChecked(selectedKeys);
    }
    wasOpen.current = open;
  }, [open, selectedKeys]);

  const canvases = useMemo(() => {
    const found: PickedCanvas[] = [];
    const seen = new Set<string>();
    const walk = (items: DirItem[]) => {
      items.forEach((item) => {
        if (isCanvasType(item.type)) {
          const key = canvasIdentityKey(item.type, Number(item.data_id));
          if (!seen.has(key)) {
            seen.add(key);
            found.push({
              resourceType: item.type,
              canvasId: Number(item.data_id),
              name: item.name,
              groups: toGroupIds(item.groups),
            });
          }
        }
        if (item.children?.length) {
          walk(item.children);
        }
      });
    };
    walk(directories);
    return found;
  }, [directories]);

  const query = keyword.trim().toLowerCase();
  const matchesQuery = (canvas: PickedCanvas) => !query || canvas.name.toLowerCase().includes(query);
  const typeCounts = useMemo(() => {
    const counts = new Map<CanvasType, number>();
    canvases.forEach((canvas) => {
      if (query && !canvas.name.toLowerCase().includes(query)) return;
      counts.set(canvas.resourceType, (counts.get(canvas.resourceType) || 0) + 1);
    });
    return counts;
  }, [canvases, query]);

  const visibleKeys = useMemo(
    () => canvases
      .filter((canvas) => {
        const matches = !query || canvas.name.toLowerCase().includes(query);
        return matches && (typeFilter === 'all' || canvas.resourceType === typeFilter);
      })
      .map((canvas) => canvasIdentityKey(canvas.resourceType, canvas.canvasId)),
    [canvases, query, typeFilter],
  );

  const treeData = useMemo(() => {
    const visible = new Set(visibleKeys);
    const build = (items: DirItem[]): DataNode[] => items.flatMap((item): DataNode[] => {
      if (isCanvasType(item.type)) {
        const key = canvasIdentityKey(item.type, Number(item.data_id));
        if (!visible.has(key)) {
          return [];
        }
        return [{
          key,
          isLeaf: true,
          title: (
            <span className="inline-flex min-w-0 items-center gap-1">
              <CanvasTypeIcon type={item.type} />
              <span className="truncate">{item.name}</span>
            </span>
          ),
        }];
      }
      const children = item.children ? build(item.children) : [];
      if (!children.length) {
        return [];
      }
      return [{
        key: `dir:${item.id}`,
        title: item.name,
        children,
      }];
    });
    return build(directories);
  }, [directories, visibleKeys]);

  const treeKeys = canvases.map((canvas) => canvasIdentityKey(canvas.resourceType, canvas.canvasId));
  const delta = selectionChangeCounts(currentItems, checked, loadFailed ? [] : treeKeys);
  const changed = delta.added > 0 || delta.removed > 0;
  const projected = projectedCarouselItemCount(currentItems, checked, loadFailed ? [] : treeKeys);
  const showRemaining = shouldShowRemainingCapacity(projected);

  const applyCheck = (keys: React.Key[] | { checked: React.Key[] }) => {
    const list = Array.isArray(keys) ? keys : keys.checked;
    const nextVisible = list.map(String).filter((key) => key.includes(':'));
    const merged = mergeCanvasChecks(checked, visibleKeys, nextVisible);
    const nextCount = projectedCarouselItemCount(currentItems, merged.keys, treeKeys);
    if (merged.blocked || nextCount > CAROUSEL_MAX_ITEMS) {
      message.warning(t('opsCarousel.itemLimit'));
      return;
    }
    setChecked(merged.keys);
  };

  const filters: { key: TypeFilter; label: string; count: number }[] = [
    {
      key: 'all',
      label: t('opsCarousel.allTypes'),
      count: canvases.filter(matchesQuery).length,
    },
    ...CANVAS_TYPE_ORDER.map((type) => ({
      key: type,
      label: t(getCanvasTypeMeta(type)?.nameKey || type),
      count: typeCounts.get(type) || 0,
    })),
  ];

  return (
    <OperateDrawer
      title={t('opsCarousel.addCanvas')}
      open={open}
      width={480}
      zIndex={1200}
      destroyOnClose
      onClose={onClose}
      footer={(
        <div className="flex w-full flex-1 items-center justify-between gap-3">
          <div className="min-w-0 text-left text-xs text-[var(--color-text-3)]">
            <div className="text-sm text-[var(--color-text-2)]">
              {t('opsCarousel.selectedCount', undefined, { count: checked.length })}
              {changed && (
                <span>
                  {' · '}
                  {t('opsCarousel.selectionDelta', undefined, { added: delta.added, removed: delta.removed })}
                </span>
              )}
            </div>
            {showRemaining && (
              <div>{t('opsCarousel.remainingCapacity', undefined, { count: remainingCapacity(projected) })}</div>
            )}
            {delta.removed > 0 && <div>{t('opsCarousel.removeDwellHint')}</div>}
            {loadFailed && <div>{t('opsCarousel.treeLoadFailed')}</div>}
          </div>
          <div className="flex shrink-0 gap-2">
            <Button onClick={onClose}>{t('common.cancel')}</Button>
            <Button
              type="primary"
              disabled={loadFailed || projected > CAROUSEL_MAX_ITEMS}
              onClick={() => {
                const selected = new Set(checked);
                onConfirm(canvases.filter((canvas) => (
                  selected.has(canvasIdentityKey(canvas.resourceType, canvas.canvasId))
                )), treeKeys);
              }}
            >
              {t('common.confirm')}
            </Button>
          </div>
        </div>
      )}
    >
      <div className="mb-3 flex items-center gap-2">
        <Input.Search
          allowClear
          value={keyword}
          placeholder={t('common.search')}
          className="min-w-0 flex-1"
          onChange={(event) => setKeyword(event.target.value)}
        />
        <Select<TypeFilter>
          className="w-36 shrink-0"
          value={typeFilter}
          popupMatchSelectWidth={false}
          getPopupContainer={(trigger) => trigger.parentElement || document.body}
          onChange={setTypeFilter}
          options={filters.map((filter) => ({
            value: filter.key,
            label: (
              <span className="inline-flex items-center gap-1">
                {filter.key !== 'all' && <CanvasTypeIcon type={filter.key} />}
                <span>{filter.label} {filter.count}</span>
              </span>
            ),
          }))}
        />
      </div>
      {treeData.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('opsCarousel.noCanvas')} />
      ) : (
        <Tree
          key={`${typeFilter}:${query}`}
          checkable
          blockNode
          defaultExpandAll
          checkedKeys={checked.filter((key) => visibleKeys.includes(key))}
          treeData={treeData}
          onCheck={applyCheck}
        />
      )}
    </OperateDrawer>
  );
};

export default CanvasPicker;
