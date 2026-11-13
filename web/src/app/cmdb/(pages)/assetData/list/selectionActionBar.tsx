'use client';

import type { ReactNode } from 'react';
import {
  BellOutlined,
  CloseOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';

export type SelectionActionBarProps = {
  count: number;
  canBatchEdit: boolean;
  showMonitorLink: boolean;
  onBatchEdit: () => void;
  onExport: () => void;
  onSubscribe: () => void;
  onMonitorLink: () => void;
  onDelete: () => void;
  onClear: () => void;
};

const actionButtonClassName =
  'flex shrink-0 flex-col items-center gap-1 rounded-md px-3 py-1 hover:bg-[color-mix(in_srgb,var(--color-bg)_14%,transparent)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-40';

const ActionButton = ({
  label,
  icon,
  danger = false,
  disabled = false,
  onClick,
}: {
  label: string;
  icon: ReactNode;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) => (
  <button
    type="button"
    className={`${actionButtonClassName}${danger ? ' text-[var(--color-fail)]' : ''}`}
    disabled={disabled}
    onClick={onClick}
  >
    <span className="text-[16px] leading-none" aria-hidden="true">{icon}</span>
    <span className="whitespace-nowrap text-[12px] leading-none">{label}</span>
  </button>
);

const Divider = () => (
  <span aria-hidden="true" className="my-1 w-px shrink-0 self-stretch bg-current opacity-25" />
);

const SelectionActionBar = ({
  count,
  canBatchEdit,
  showMonitorLink,
  onBatchEdit,
  onExport,
  onSubscribe,
  onMonitorLink,
  onDelete,
  onClear,
}: SelectionActionBarProps) => {
  const { t } = useTranslation();
  if (count <= 0) return null;

  const summary = `${t('common.checked')} ${count} ${t('common.items')}`;

  return (
    <div
      role="toolbar"
      aria-label={summary}
      className="absolute bottom-16 left-1/2 z-20 flex w-max max-w-[calc(100%-2rem)] -translate-x-1/2 items-center gap-1 overflow-x-auto rounded-full bg-[var(--color-text-1)] px-2 py-1.5 text-[var(--color-bg)] shadow-[0_4px_12px_rgba(0,0,0,0.15)]"
    >
      <span className="shrink-0 px-3 text-[12px] font-medium tabular-nums">{summary}</span>
      <Divider />
      <PermissionWrapper requiredPermissions={['Edit']}>
        <ActionButton
          label={t('batchEdit')}
          icon={<EditOutlined />}
          disabled={!canBatchEdit}
          onClick={onBatchEdit}
        />
      </PermissionWrapper>
      <ActionButton label={t('export')} icon={<ExportOutlined />} onClick={onExport} />
      <ActionButton label={t('subscription.subscribe')} icon={<BellOutlined />} onClick={onSubscribe} />
      {showMonitorLink ? (
        <PermissionWrapper requiredPermissions={['Edit']}>
          <ActionButton
            label={t('Model.systemLinkageBatchSync')}
            icon={<LinkOutlined />}
            onClick={onMonitorLink}
          />
        </PermissionWrapper>
      ) : null}
      <PermissionWrapper requiredPermissions={['Delete']}>
        <ActionButton
          danger
          label={t('common.batchDelete')}
          icon={<DeleteOutlined />}
          onClick={onDelete}
        />
      </PermissionWrapper>
      <Divider />
      <button
        type="button"
        aria-label={t('selectionBarClear')}
        className="flex size-8 shrink-0 items-center justify-center rounded-full text-[16px] text-[var(--color-bg)] hover:bg-[color-mix(in_srgb,var(--color-bg)_14%,transparent)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
        onClick={onClear}
      >
        <CloseOutlined aria-hidden="true" />
      </button>
    </div>
  );
};

export default SelectionActionBar;
