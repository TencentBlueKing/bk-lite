'use client';

import type { CSSProperties, ReactNode } from 'react';
import { Button } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import HttpMethodBadge from '@/components/http-method-badge';
import { useCopy } from '@/hooks/useCopy';
import { useTranslation } from '@/utils/i18n';

export interface HttpEndpointDisplayProps {
  method?: string | null;
  endpoint?: string | null;
  className?: string;
  endpointClassName?: string;
  placeholder?: ReactNode;
  badgeClassName?: string;
  badgeStyle?: CSSProperties;
  copyDisabled?: boolean;
  copySuccessMessage?: string;
  showCopySuccessMessage?: boolean;
}

const joinClassName = (...values: Array<string | undefined>) =>
  values.filter(Boolean).join(' ');

export default function HttpEndpointDisplay({
  method = 'GET',
  endpoint,
  className,
  endpointClassName,
  placeholder = '--',
  badgeClassName,
  badgeStyle,
  copyDisabled = false,
}: HttpEndpointDisplayProps) {
  const { t } = useTranslation();
  const { copy } = useCopy();

  const hasEndpoint = Boolean(endpoint);
  const displayValue = hasEndpoint ? endpoint : placeholder;

  return (
    <div
      className={joinClassName(
        'flex w-full items-center gap-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-3 py-2',
        className,
      )}
    >
      <HttpMethodBadge
        method={method || 'GET'}
        className={joinClassName('m-0 shrink-0 border-0', badgeClassName)}
        style={badgeStyle}
      />
      <div className="min-w-0 flex-1 rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-1.5">
        <span
          className={joinClassName(
            'block min-w-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[13px] text-[var(--color-text-1)]',
            endpointClassName,
          )}
          title={typeof displayValue === 'string' ? displayValue : undefined}
        >
          {displayValue}
        </span>
      </div>
      <Button
        type="default"
        icon={<CopyOutlined aria-hidden="true" />}
        aria-label={t('common.copy')}
        className="shrink-0"
        disabled={!hasEndpoint || copyDisabled}
        onClick={() => copy(endpoint || '')}
      >
        {t('common.copy')}
      </Button>
    </div>
  );
}
