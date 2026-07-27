import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';
import { useTranslation } from '@/utils/i18n';

export interface NodeManagerRuntimeStatusBadgeProps {
  status?: number | string | null;
  label?: React.ReactNode;
  count?: number;
  tone?: keyof typeof STATUS_STYLES;
  className?: string;
}

const STATUS_STYLES = {
  success: {
    textColor: 'var(--color-success)',
    backgroundColor:
      'color-mix(in srgb, var(--color-success) 12%, transparent)',
  },
  error: {
    textColor: 'var(--color-error)',
    backgroundColor:
      'color-mix(in srgb, var(--color-error) 12%, transparent)',
  },
  warning: {
    textColor: 'var(--color-warning)',
    backgroundColor:
      'color-mix(in srgb, var(--color-warning) 12%, transparent)',
  },
  processing: {
    textColor: 'var(--color-primary)',
    backgroundColor:
      'color-mix(in srgb, var(--color-primary) 12%, transparent)',
  },
  neutral: {
    textColor: 'var(--color-text-2)',
    backgroundColor:
      'color-mix(in srgb, var(--color-fill-5) 32%, transparent)',
  },
} as const;

const normalizeStatus = (status?: number | string | null) => {
  switch (String(status ?? '1')) {
    case '0':
    case 'success':
    case 'installed':
      return 'success';
    case '2':
    case 'error':
      return 'error';
    case '3':
    case '12':
    case 'timeout':
      return 'warning';
    case '10':
    case 'running':
    case 'installing':
    case 'waiting':
    case 'processing':
      return 'processing';
    case '1':
    case '4':
    case '11':
    case 'unknown':
    case 'pending':
    default:
      return 'neutral';
  }
};

const fallbackLabel = (
  status: ReturnType<typeof normalizeStatus>,
  t: ReturnType<typeof useTranslation>['t']
) => {
  switch (status) {
    case 'success':
      return t('node-manager.cloudregion.node.normal');
    case 'error':
      return t('node-manager.cloudregion.node.error');
    case 'warning':
      return t('node-manager.cloudregion.node.stopped');
    case 'processing':
      return t('node-manager.cloudregion.node.installing');
    default:
      return t('node-manager.cloudregion.node.unknown');
  }
};

const NodeManagerRuntimeStatusBadge: React.FC<
  NodeManagerRuntimeStatusBadgeProps
> = ({ status, label, count, tone, className = '' }) => {
  const { t } = useTranslation();
  const normalized = normalizeStatus(status);
  const palette = STATUS_STYLES[tone || normalized];
  const resolvedLabel = label || fallbackLabel(normalized, t);

  return (
    <StatusBadgeShell
      className={className}
      label={
        typeof count === 'number' ? `${resolvedLabel}: ${count}` : resolvedLabel
      }
      palette={palette}
    />
  );
};

export default NodeManagerRuntimeStatusBadge;
