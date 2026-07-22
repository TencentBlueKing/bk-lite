'use client';

import React from 'react';
import { Button } from 'antd';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';

interface PrivateKeyUploadFieldProps {
  fileName?: string;
  onFileLoaded: (content: string, fileName: string) => void;
  onClear: () => void;
  disabled?: boolean;
  buttonClassName?: string;
  previewClassName?: string;
}

const PrivateKeyUploadField = ({
  fileName,
  onFileLoaded,
  onClear,
  disabled,
  buttonClassName,
  previewClassName = 'overflow-hidden text-ellipsis whitespace-nowrap',
}: PrivateKeyUploadFieldProps) => {
  const { t } = useTranslation();

  if (fileName) {
    return (
      <div className="inline-flex max-w-full items-center gap-2 text-[var(--color-text-1)] group">
        <EllipsisWithTooltip text={fileName} className={previewClassName} />
        <span
          className="cursor-pointer opacity-0 transition-opacity flex-shrink-0 group-hover:opacity-100"
          style={{
            fontSize: 16,
            color: 'var(--color-primary)',
            fontWeight: 'bold',
          }}
          onClick={onClear}
          title={t('common.delete')}
        >
          ×
        </span>
      </div>
    );
  }

  return (
    <Button
      disabled={disabled}
      className={buttonClassName}
      onClick={() => {
        const input = document.createElement('input');
        input.type = 'file';
        input.onchange = (event: Event) => {
          const target = event.target as HTMLInputElement | null;
          const file = target?.files?.[0];
          if (!file) return;

          const reader = new FileReader();
          reader.onload = (loadEvent) => {
            const content = loadEvent.target?.result;
            if (typeof content === 'string') {
              onFileLoaded(content, file.name);
            }
          };
          reader.readAsText(file);
        };
        input.click();
      }}
    >
      {t('node-manager.cloudregion.node.uploadPrivateKey')}
    </Button>
  );
};

export default PrivateKeyUploadField;
