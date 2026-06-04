import React from 'react';
import { useTranslation } from '@/utils/i18n';
import { getRecordEntries } from '../shared/tableLikeData';

interface EventTableDetailProps {
  record: Record<string, unknown>;
}

export const EventTableDetail: React.FC<EventTableDetailProps> = ({
  record,
}) => {
  const { t } = useTranslation();
  const entries = getRecordEntries(record);

  return (
    <div className="overflow-hidden rounded-lg border border-(--color-border-1) bg-(--color-bg-1)">
      <div className="max-h-72 overflow-auto">
        <div className="sticky top-0 z-1 grid grid-cols-[180px_minmax(0,1fr)] border-b border-(--color-border-1) bg-(--color-bg-2) px-3 py-2 text-[11px] font-medium text-(--color-text-3)">
          <span>{t('dashboard.filterFieldKey')}</span>
          <span>{t('common.value')}</span>
        </div>
        {entries.map((field, index) => (
          <div
            key={field.key}
            className="grid grid-cols-[180px_minmax(0,1fr)] border-b border-(--color-border-1) px-3 py-2 text-xs last:border-b-0"
            style={{
              backgroundColor:
                index % 2 === 0
                  ? 'var(--color-bg-1)'
                  : 'rgba(15, 23, 42, 0.02)',
            }}
          >
            <span
              className="truncate pr-3 font-mono text-[11px] text-(--color-text-3)"
              title={field.key}
            >
              {field.key}
            </span>
            <pre className="m-0 whitespace-pre-wrap break-all font-sans text-xs leading-5 text-(--color-text-1)">
              {field.value}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
};
