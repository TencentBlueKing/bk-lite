import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';
import { useTranslation } from '@/utils/i18n';

export type CustomReportingMode = 'quick' | 'standard';

export interface CustomReportingModeBadgeProps {
  mode?: CustomReportingMode | string | null;
  label?: React.ReactNode;
  className?: string;
}

const MODE_STYLES = {
  quick: {
    textColor: '#722ed1',
    backgroundColor: 'color-mix(in srgb, #722ed1 12%, transparent)',
  },
  standard: {
    textColor: 'var(--color-text-2)',
    backgroundColor: 'color-mix(in srgb, var(--color-fill-5) 32%, transparent)',
  },
} as const;

const normalizeMode = (mode?: CustomReportingModeBadgeProps['mode']) =>
  String(mode || 'standard').toLowerCase() === 'quick' ? 'quick' : 'standard';

const CustomReportingModeBadge: React.FC<CustomReportingModeBadgeProps> = ({
  mode,
  label,
  className = '',
}) => {
  const { t } = useTranslation();
  const normalized = normalizeMode(mode);
  const palette = MODE_STYLES[normalized];
  const resolvedLabel =
    label ||
    (normalized === 'quick'
      ? t('CustomReporting.modeQuick')
      : t('CustomReporting.modeStandard'));

  return (
    <StatusBadgeShell
      label={resolvedLabel}
      className={className}
      palette={palette}
    />
  );
};

export default CustomReportingModeBadge;
