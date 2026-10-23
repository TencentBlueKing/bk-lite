'use client';

import { useEffect, useMemo, useState } from 'react';
import { Button, Popconfirm, Spin, Tag, Typography } from 'antd';
import { DisconnectOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import type {
  ArchitectureBinding,
  ArchitectureNodeStatusItem,
  BindingSearchHit,
  BindingSearchPage,
  ModelOption,
} from '../binding/model';
import { bindingDisplay, bindingModelLabel } from '../binding/model';
import {
  bindingStatusLoading,
  DEFAULT_ICON_TITLE,
  STATUS_DOT_COLOR,
  STATUS_LABEL_KEY,
} from '../binding/status';
import ResourcePicker from './resourcePicker';

interface ResourceBindingDrawerProps {
  open: boolean;
  binding: ArchitectureBinding | null;
  status: ArchitectureNodeStatusItem | null;
  /** Phase of the edit-mode status request; a failed request stops the loading state. */
  statusPhase: 'idle' | 'ready' | 'failed';
  /** Stored name of the icon being bound. */
  iconName: string;
  modelName: string;
  models: ModelOption[];
  onSearch: (
    keyword: string,
    modelId: string,
    page: number,
    pageSize: number,
  ) => Promise<BindingSearchPage>;
  onBind: (hit: BindingSearchHit) => void;
  onUnbind: () => void;
  onClose: () => void;
}

const EMPTY_UUIDS: ReadonlySet<string> = new Set();

const ResourceBindingDrawer = ({
  open,
  binding,
  status,
  statusPhase,
  iconName,
  modelName,
  models,
  onSearch,
  onBind,
  onUnbind,
  onClose,
}: ResourceBindingDrawerProps) => {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<BindingSearchHit | null>(null);
  const bound = Boolean(binding);
  const statusLoading = bindingStatusLoading(bound, status, statusPhase);
  const boundUuid = binding?.inst_uuid ?? '';
  const boundModelId = binding?.model_id ?? '';
  const disabledUuids = useMemo(
    () => (boundUuid ? new Set([boundUuid]) : EMPTY_UUIDS),
    [boundUuid],
  );

  useEffect(() => {
    if (!open) return;
    setSelected(null);
  }, [open, boundUuid, boundModelId]);

  const display = bindingDisplay(status, modelName);
  const blockedText = display.blocked === 'invalid'
    ? t('opsAnalysis.architecture.bindingInvalid')
    : display.blocked === 'forbidden'
      ? t('opsAnalysis.architecture.bindingForbidden')
      : t('opsAnalysis.architecture.bindingUnknown');
  const cardType = display.typeName || (binding ? bindingModelLabel(models, binding.model_id) : modelName);
  const statusKey = STATUS_LABEL_KEY[status?.status ?? 'unknown'];
  const statusDot = STATUS_DOT_COLOR[status?.status ?? 'unknown'];
  const shownIconName = iconName.trim() && iconName.trim() !== DEFAULT_ICON_TITLE
    ? iconName.trim()
    : t('opsAnalysis.architecture.unnamedIcon');
  const selectedParts = selected
    ? (() => {
      const marker = '\u0000';
      const [before = '', after = ''] = t(
        'opsAnalysis.architecture.bindingSelected',
        undefined,
        { name: marker },
      ).split(marker);
      return { before, name: selected.inst_name || selected.inst_uuid, after };
    })()
    : null;

  const boundCard = bound ? (
    <section className="shrink-0">
      <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-fill-1)]/60 px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            {statusLoading ? (
              <Spin size="small" />
            ) : (
              <span
                className={`truncate text-sm ${display.blocked
                  ? 'text-[var(--color-text-3)]'
                  : 'font-semibold text-[var(--color-text-1)]'}`}
                title={display.blocked ? blockedText : display.name}
              >
                {display.blocked ? blockedText : display.name}
              </span>
            )}
            {cardType ? <Tag color="blue" className="m-0 shrink-0">{cardType}</Tag> : null}
          </div>
          <Popconfirm
            title={t('opsAnalysis.architecture.bindingUnbindConfirm')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={onUnbind}
          >
            <Button type="text" danger size="small" icon={<DisconnectOutlined />}>
              {t('opsAnalysis.architecture.bindingUnbind')}
            </Button>
          </Popconfirm>
        </div>
        <div className="mt-2 flex items-center gap-3 text-xs text-[var(--color-text-3)]">
          <span className="flex min-w-0 items-center gap-1 font-mono">
            <span className="shrink-0">{t('opsAnalysis.architecture.bindingCardId')}</span>
            <Typography.Text
              className="min-w-0 font-mono text-xs text-[var(--color-text-3)]"
              ellipsis={{ tooltip: boundUuid }}
              copyable={{ text: boundUuid }}
            >
              {boundUuid}
            </Typography.Text>
          </span>
          <span className="flex shrink-0 items-center gap-1.5 text-[var(--color-text-2)]">
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: statusDot }} />
            {t(statusKey)}
          </span>
        </div>
      </div>
    </section>
  ) : null;

  return (
    <OperateModal
      open={open}
      width={760}
      centered
      destroyOnHidden
      title={(
        <span className="flex min-w-0 flex-col">
          <span>{t('opsAnalysis.architecture.bindingDrawerTitle')}</span>
          <span className="mt-0.5 truncate text-xs font-normal text-[var(--color-text-3)]" title={shownIconName}>
            {t('opsAnalysis.architecture.bindingIconName', undefined, { name: shownIconName })}
          </span>
        </span>
      )}
      onCancel={onClose}
      footer={(
        <div className="flex w-full items-center justify-between gap-3">
          <span className="min-w-0 truncate text-xs text-[var(--color-text-3)]">
            {selectedParts ? (
              <>
                {selectedParts.before}
                <span className="font-medium text-[var(--color-primary)]">{selectedParts.name}</span>
                {selectedParts.after}
              </>
            ) : null}
          </span>
          <span className="flex shrink-0 gap-2">
            <Button onClick={onClose}>{t('opsAnalysis.architecture.bindingCancel')}</Button>
            <Button type="primary" disabled={!selected} onClick={() => selected && onBind(selected)}>
              {bound
                ? t('opsAnalysis.architecture.bindingConfirmReplace')
                : t('opsAnalysis.architecture.bindingConfirm')}
            </Button>
          </span>
        </div>
      )}
    >
      <div className="flex flex-col gap-4" data-testid="architecture-binding-drawer">
        {boundCard}
        <section className="flex flex-col">
          <div className="mb-2 text-xs font-medium text-[var(--color-text-3)]">
            {bound ? t('opsAnalysis.architecture.bindingReplace') : t('opsAnalysis.architecture.bindingPick')}
          </div>
          <ResourcePicker
            active={open}
            models={models}
            initialModelId={boundModelId}
            mode="single"
            disabledUuids={disabledUuids}
            selected={selected ? [selected] : []}
            onSelectedChange={(hits) => setSelected(hits[0] ?? null)}
            onSearch={onSearch}
            scrollY="320"
          />
        </section>
      </div>
    </OperateModal>
  );
};

export default ResourceBindingDrawer;
