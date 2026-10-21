'use client';

import React from 'react';
import { Button, message, Tooltip } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';

interface InstUuidCopyProps {
  value?: string | null;
  showLabel?: boolean;
  empty?: 'hide' | 'dash';
  /** 详情里需要看全貌时换行，列表单元格仍截断。 */
  wrap?: boolean;
  className?: string;
  rowClassName?: string;
}

const InstUuidCopy: React.FC<InstUuidCopyProps> = ({
  value,
  showLabel = false,
  empty = 'dash',
  wrap = false,
  className = '',
  rowClassName = '',
}) => {
  const { t } = useTranslation();
  const text = String(value || '').trim();
  if (!text) {
    if (empty === 'hide') return null;
    return <span className="text-[var(--color-text-3)]">--</span>;
  }

  const copy = (event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    navigator.clipboard.writeText(text).then(
      () => message.success(t('successfulCopied')),
      () => message.error(t('common.copyFailed')),
    );
  };

  const copyButton = (
    <Tooltip title={t('common.copy')}>
      <Button
        type="text"
        size="small"
        aria-label={t('common.copy')}
        icon={<CopyOutlined aria-hidden="true" />}
        className="!inline-flex !h-4 !w-4 items-center justify-center !p-0 !leading-none text-[var(--color-text-3)] [&_.anticon]:text-[12px]"
        onClick={copy}
      />
    </Tooltip>
  );

  if (wrap) {
    return (
      <div className={`flex justify-end ${rowClassName}`}>
        <span className={`inline-flex items-center gap-1 text-[var(--color-text-3)] ${className}`}>
          {showLabel ? `${t('Model.instanceUuid')} ${text}` : text}
          {copyButton}
        </span>
      </div>
    );
  }

  return (
    <span className={`flex min-w-0 items-center gap-1 ${rowClassName}`}>
      <span className="min-w-0 flex-1">
        <EllipsisWithTooltip
          text={showLabel ? `${t('Model.instanceUuid')} ${text}` : text}
          className={`block w-full overflow-hidden text-ellipsis whitespace-nowrap text-[var(--color-text-3)] ${className}`}
        />
      </span>
      {copyButton}
    </span>
  );
};

export default InstUuidCopy;
