'use client';

import { useEffect, useState } from 'react';
import { Button } from 'antd';
import OperateDrawer from '@/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import type { BindingSearchHit, BindingSearchPage, ModelOption } from '../binding/model';
import ResourcePicker from './resourcePicker';

interface ResourceInsertDrawerProps {
  open: boolean;
  models: ModelOption[];
  placedUuids: ReadonlySet<string>;
  onSearch: (
    keyword: string,
    modelId: string,
    page: number,
    pageSize: number,
  ) => Promise<BindingSearchPage>;
  onConfirm: (hits: BindingSearchHit[]) => void;
  onClose: () => void;
}

const ResourceInsertDrawer = ({
  open,
  models,
  placedUuids,
  onSearch,
  onConfirm,
  onClose,
}: ResourceInsertDrawerProps) => {
  const { t } = useTranslation();
  const [picked, setPicked] = useState<BindingSearchHit[]>([]);

  useEffect(() => {
    if (!open) return;
    setPicked([]);
  }, [open]);

  const readyHits = picked.filter((hit) => !placedUuids.has(hit.inst_uuid));

  return (
    <OperateDrawer
      open={open}
      width={760}
      destroyOnHidden
      title={t('opsAnalysis.architecture.insertDrawerTitle')}
      onClose={onClose}
      classNames={{ body: 'flex min-h-0 flex-col' }}
      styles={{ body: { overflow: 'hidden', padding: '20px 24px' } }}
      footer={(
        <div className="flex w-full items-center justify-end gap-2">
          <Button onClick={onClose}>{t('opsAnalysis.architecture.bindingCancel')}</Button>
          <Button
            type="primary"
            disabled={readyHits.length === 0}
            onClick={() => onConfirm(readyHits)}
          >
            {t('opsAnalysis.architecture.insertConfirm')}
          </Button>
        </div>
      )}
    >
      <div className="flex h-full min-h-0 flex-1 flex-col" data-testid="architecture-insert-drawer">
        <ResourcePicker
          active={open}
          models={models}
          mode="multiple"
          disabledUuids={placedUuids}
          selected={picked}
          onSelectedChange={setPicked}
          onSearch={onSearch}
          scrollY="calc(100vh - 280px)"
        />
      </div>
    </OperateDrawer>
  );
};

export default ResourceInsertDrawer;
