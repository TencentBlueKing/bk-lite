import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';
import { useTranslation } from '@/utils/i18n';

export interface MonitorAlertTypeBadgeProps {
  alertType?: string | null;
  label?: React.ReactNode;
  className?: string;
}

const MONITOR_ALERT_TYPE_I18N_KEYS: Record<string, string> = {
  alert: 'monitor.events.alertTypeThreshold',
  no_data: 'monitor.events.alertTypeNoData',
};

const MonitorAlertTypeBadge: React.FC<MonitorAlertTypeBadgeProps> = ({
  alertType,
  label,
  className = '',
}) => {
  const { t } = useTranslation();
  const resolvedLabel =
    label ||
    (alertType
      ? t(MONITOR_ALERT_TYPE_I18N_KEYS[alertType] || alertType)
      : '--');

  return (
    <StatusBadgeShell
      className={className}
      label={resolvedLabel}
      palette={{
        textColor: 'var(--color-text-2)',
        backgroundColor:
          'color-mix(in srgb, var(--color-text-4) 14%, transparent)',
      }}
    />
  );
};

export default MonitorAlertTypeBadge;
