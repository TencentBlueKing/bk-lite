import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';
import { useTranslation } from '@/utils/i18n';

export interface JobDriverBadgeProps {
  driver?: string | null;
  label?: React.ReactNode;
  className?: string;
}

const DRIVER_STYLES = {
  'nats-executor': {
    textColor: 'var(--color-primary)',
    backgroundColor: 'color-mix(in srgb, var(--color-primary) 12%, transparent)',
  },
  sidecar: {
    textColor: '#2f54eb',
    backgroundColor: 'color-mix(in srgb, #2f54eb 12%, transparent)',
  },
  ansible: {
    textColor: 'var(--color-success)',
    backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
  },
  ssh: {
    textColor: '#d46b08',
    backgroundColor: 'color-mix(in srgb, #d46b08 12%, transparent)',
  },
} as const;

const DRIVER_I18N_KEYS: Record<string, string> = {
  'nats-executor': 'job.driverNatsExecutor',
  ansible: 'job.driverAnsible',
  ssh: 'job.driverSSH',
};

const normalizeDriver = (driver?: string | null) => (driver || '').toLowerCase();

const JobDriverBadge: React.FC<JobDriverBadgeProps> = ({
  driver,
  label,
  className = '',
}) => {
  const { t } = useTranslation();
  const normalized = normalizeDriver(driver);
  const palette =
    DRIVER_STYLES[normalized as keyof typeof DRIVER_STYLES] || {
      textColor: 'var(--color-text-2)',
      backgroundColor:
        'color-mix(in srgb, var(--color-text-4) 14%, transparent)',
    };

  const resolvedLabel =
    label ||
    (normalized
      ? DRIVER_I18N_KEYS[normalized]
        ? t(DRIVER_I18N_KEYS[normalized])
        : normalized === 'sidecar'
          ? 'Sidecar'
          : driver
      : '--');

  return (
    <StatusBadgeShell
      className={className}
      label={resolvedLabel}
      palette={palette}
    />
  );
};

export default JobDriverBadge;
