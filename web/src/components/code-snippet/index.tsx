'use client';

import type { CSSProperties } from 'react';
import { Button } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { useCopy } from '@/hooks/useCopy';
import { useTranslation } from '@/utils/i18n';

export interface CodeSnippetProps {
  value?: string;
  className?: string;
  copyable?: boolean;
  copyDisabled?: boolean;
  maxHeight?: CSSProperties['maxHeight'];
  tone?: 'default' | 'inverse';
}

const joinClassName = (...values: Array<string | undefined>) =>
  values.filter(Boolean).join(' ');

const toneClassMap = {
  default: {
    wrapper:
      'rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]',
    code: 'text-[var(--color-text-1)]',
    copy:
      'text-[var(--color-text-3)] hover:!text-[var(--color-primary)]',
  },
  inverse: {
    wrapper: 'rounded-lg bg-[#1e1e1e]',
    code: 'text-[#d4d4d4]',
    copy: 'text-white/60 hover:!text-white',
  },
} as const;

export default function CodeSnippet({
  value = '',
  className,
  copyable = false,
  copyDisabled = false,
  maxHeight,
  tone = 'default',
}: CodeSnippetProps) {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const toneClasses = toneClassMap[tone];

  return (
    <div
      className={joinClassName(
        'relative overflow-hidden px-5 py-4',
        toneClasses.wrapper,
        className,
      )}
    >
      {copyable ? (
        <Button
          type="text"
          size="small"
          aria-label={t('common.copy')}
          icon={<CopyOutlined aria-hidden="true" />}
          disabled={copyDisabled}
          className={joinClassName(
            'absolute right-3 top-3 z-10',
            toneClasses.copy,
          )}
          onClick={() => copy(value)}
        />
      ) : null}
      <pre
        className={joinClassName(
          'm-0 overflow-auto pr-10 font-mono text-[13px] leading-6 whitespace-pre-wrap break-all',
          toneClasses.code,
        )}
        style={maxHeight ? { maxHeight } : undefined}
      >
        <code>{value}</code>
      </pre>
    </div>
  );
}
