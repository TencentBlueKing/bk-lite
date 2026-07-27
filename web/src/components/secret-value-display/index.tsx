'use client';

import type { ReactNode } from 'react';
import { CopyOutlined } from '@ant-design/icons';
import { useCopy } from '@/hooks/useCopy';
import { useTranslation } from '@/utils/i18n';

export interface SecretValueDisplayProps {
  value?: string | null;
  placeholder?: ReactNode;
  masked?: boolean;
  maskText?: ReactNode;
  copyable?: boolean;
  className?: string;
}

const SecretValueDisplay = ({
  value,
  placeholder = '--',
  masked = true,
  maskText = '******************',
  copyable = true,
  className = '',
}: SecretValueDisplayProps) => {
  const { t } = useTranslation();
  const { copy } = useCopy();

  if (!value) {
    return <span className={className}>{placeholder}</span>;
  }

  return (
    <span className={`inline-flex items-center gap-2 ${className}`.trim()}>
      <span className="font-mono">
        {masked ? maskText : value}
      </span>
      {copyable ? (
        <CopyOutlined
          aria-label={t('common.copy')}
          className="cursor-pointer text-[var(--color-text-3)] transition-colors hover:text-[var(--color-primary)]"
          onClick={() => copy(value)}
        />
      ) : null}
    </span>
  );
};

export default SecretValueDisplay;
