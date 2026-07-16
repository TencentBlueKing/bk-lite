import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';
import { useTranslation } from '@/utils/i18n';

export interface MonitorReportingStatusBadgeProps {
  status?: string | null;
  label?: React.ReactNode;
  className?: string;
}

const normalizeStatus = (status?: string | null) => {
  const normalized = (status || '').toLowerCase();
  if (normalized === 'normal' || normalized === 'online') {
    return 'normal';
  }
  return 'unavailable';
};

const MonitorReportingStatusBadge: React.FC<
  MonitorReportingStatusBadgeProps
> = ({ status, label, className = '' }) => {
  const { t } = useTranslation();
  const normalized = normalizeStatus(status);
  const isNormal = normalized === 'normal';

  return (
    <StatusBadgeShell
      className={className}
      label={
        label ||
        (isNormal
          ? t('monitor.integrations.normal')
          : t('monitor.integrations.unavailable'))
      }
      palette={{
        textColor: isNormal ? 'var(--color-success)' : 'var(--color-text-3)',
        backgroundColor: isNormal
          ? 'color-mix(in srgb, var(--color-success) 12%, transparent)'
          : 'color-mix(in srgb, var(--color-text-4) 18%, transparent)',
      }}
    />
  );
};

export default MonitorReportingStatusBadge;
