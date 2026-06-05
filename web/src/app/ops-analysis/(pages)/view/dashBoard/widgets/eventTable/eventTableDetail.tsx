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
  const panelBorderColor =
    'color-mix(in srgb, var(--color-primary) 6%, var(--color-border-1))';
  const panelBackground = 'var(--color-bg-1)';
  const headerBackground =
    'linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 4%, var(--color-bg-1)) 0%, color-mix(in srgb, var(--color-primary) 2%, var(--color-bg-2)) 100%)';
  const stripeBackground =
    'color-mix(in srgb, var(--color-primary) 1%, var(--color-bg-1))';
  const keyCellBackground =
    'color-mix(in srgb, var(--color-primary) 2%, var(--color-bg-1))';

  return (
    <div
      className="overflow-hidden rounded-xl border bg-(--color-bg-1) shadow-[0_2px_8px_rgba(15,23,42,0.03)]"
      style={{
        borderColor: panelBorderColor,
        background: panelBackground,
      }}
    >
      <div className="max-h-72 overflow-auto">
        <div
          className="sticky top-0 z-1 grid grid-cols-[180px_minmax(0,1fr)] border-b px-3 py-2 text-[11px] font-semibold tracking-[0.01em]"
          style={{
            borderColor: panelBorderColor,
            background: headerBackground,
            color:
              'color-mix(in srgb, var(--color-primary) 34%, var(--color-text-1))',
          }}
        >
          <span className="pr-3">{t('dashboard.filterFieldKey')}</span>
          <span>{t('common.value')}</span>
        </div>
        {entries.map((field, index) => (
          <div
            key={field.key}
            className="grid grid-cols-[180px_minmax(0,1fr)] border-b text-xs last:border-b-0"
            style={{
              borderColor:
                'color-mix(in srgb, var(--color-primary) 4%, var(--color-border-1))',
              backgroundColor:
                index % 2 === 0 ? 'var(--color-bg-1)' : stripeBackground,
            }}
          >
            <span
              className="truncate border-r px-3 py-2.5 font-mono text-[11px] font-medium leading-5"
              style={{
                borderColor:
                  'color-mix(in srgb, var(--color-primary) 4%, var(--color-border-1))',
                backgroundColor: keyCellBackground,
                color:
                  'color-mix(in srgb, var(--color-primary) 22%, var(--color-text-2))',
              }}
              title={field.key}
            >
              {field.key}
            </span>
            <pre className="m-0 px-3 py-2.5 whitespace-pre-wrap break-all font-sans text-xs leading-5 text-(--color-text-1)">
              {field.value}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
};
