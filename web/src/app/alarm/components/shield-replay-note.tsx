import React from 'react';
import { useTranslation } from '@/utils/i18n';
import { shieldReplaySourceEventId } from '@/app/alarm/utils/eventRawData';

const ShieldReplayNote: React.FC<{ raw?: unknown; className?: string }> = ({ raw, className }) => {
  const { t } = useTranslation();
  const sourceEventId = shieldReplaySourceEventId(raw);
  if (!sourceEventId) {
    return null;
  }
  return (
    <p className={className || 'mt-1 text-xs text-[var(--color-text-3)]'}>
      {t('alarms.shieldReplayNote', undefined, { id: sourceEventId })}
    </p>
  );
};

export default ShieldReplayNote;
