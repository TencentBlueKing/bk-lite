import React from 'react';
import { ApiOutlined, ToolOutlined } from '@ant-design/icons';
import StatusBadgeShell from '@/components/status-badge-shell';
import { useTranslation } from '@/utils/i18n';

export interface MonitorIntegrationAccessBadgeProps {
  mode?: string | null;
  label?: React.ReactNode;
  className?: string;
}

const isManualMode = (mode?: string | null) => (mode || '').toLowerCase() === 'manual';

const MonitorIntegrationAccessBadge: React.FC<
  MonitorIntegrationAccessBadgeProps
> = ({ mode, label, className = '' }) => {
  const { t } = useTranslation();
  const manual = isManualMode(mode);
  const resolvedLabel =
    label ||
    (manual
      ? t('monitor.integrations.manualAccess')
      : t('monitor.integrations.autoAccess'));

  return (
    <StatusBadgeShell
      className={className}
      label={
        <span className="inline-flex items-center gap-1">
          {manual ? <ToolOutlined /> : <ApiOutlined />}
          <span>{resolvedLabel}</span>
        </span>
      }
      palette={{
        textColor: 'var(--color-primary)',
        backgroundColor:
          'color-mix(in srgb, var(--color-primary) 12%, transparent)',
      }}
    />
  );
};

export default MonitorIntegrationAccessBadge;
