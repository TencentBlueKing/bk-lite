'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Key, ReactNode } from 'react';
import { Button, Dropdown, message } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { DEFAULT_SELECTION_COLUMN_WIDTH } from '@/components/custom-table/columnLayout';
import type { BatchResource } from '@/app/job/types';
import { useTranslation } from '@/utils/i18n';

const MAX_SELECTED = 1000;

interface SelectionOptions {
  resource: BatchResource;
  total: number;
  pageSize: number;
  loading: boolean;
  loadIds: () => Promise<{ ids: number[] }>;
}

export default function useBatchSelection({ resource, total, pageSize, loading, loadIds }: SelectionOptions) {
  const { t } = useTranslation();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [selectingAll, setSelectingAll] = useState(false);
  const selectionVersion = useRef(0);
  useEffect(() => () => { selectionVersion.current += 1; }, []);

  const invalidate = useCallback(() => {
    selectionVersion.current += 1;
    setSelectingAll(false);
  }, []);
  const clearSelection = useCallback(() => {
    invalidate();
    setSelectedIds([]);
  }, [invalidate]);
  const removeFromSelection = (id: number) => {
    invalidate();
    setSelectedIds(current => current.filter(selectedId => selectedId !== id));
  };
  const resourceName = t(`job.targetOrganizations.resource.${resource}`);
  const validateCount = (size: number) => {
    if (size <= MAX_SELECTED) return true;
    message.warning(t('job.targetOrganizations.selectionLimit', '', { limit: MAX_SELECTED, resource: resourceName }));
    return false;
  };
  const replaceSelection = (ids: number[]) => {
    invalidate();
    if (validateCount(ids.length)) setSelectedIds(ids);
  };
  const selectFiltered = async () => {
    if (!validateCount(total)) return;
    const version = ++selectionVersion.current;
    setSelectingAll(true);
    try {
      const { ids } = await loadIds();
      if (version === selectionVersion.current) replaceSelection(ids);
    } catch {
      // The request interceptor displays the selection failure.
    } finally {
      if (version === selectionVersion.current) setSelectingAll(false);
    }
  };

  const multiplePages = total > pageSize;
  const rowSelection = {
    columnWidth: multiplePages ? 56 : DEFAULT_SELECTION_COLUMN_WIDTH,
    columnTitle: (checkbox: ReactNode) => multiplePages ? (
      <span className="inline-flex items-center">
        {checkbox}
        <Dropdown
          trigger={['click']}
          menu={{ items: [
            {
              key: 'all',
              label: t('job.targetOrganizations.selectAll', '', { count: total, resource: resourceName }),
              disabled: loading || selectingAll || selectedIds.length === total,
              onClick: selectFiltered,
            },
            {
              key: 'clear',
              label: t('job.targetOrganizations.clear'),
              disabled: !selectedIds.length && !selectingAll,
              onClick: clearSelection,
            },
          ] }}
        >
          <Button type="text" size="small" icon={<DownOutlined />} aria-label={t('job.targetOrganizations.selectionOptions')} />
        </Dropdown>
      </span>
    ) : checkbox,
    selectedRowKeys: selectedIds,
    preserveSelectedRowKeys: true,
    onChange: (keys: Key[]) => replaceSelection(keys.map(Number)),
  };

  return { selectedIds, selectingAll, selectionVersion, clearSelection, removeFromSelection, rowSelection };
}
