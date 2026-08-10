import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

export interface ExecutionStatusBadgeProps {
  status?: string | null;
  label?: React.ReactNode;
  className?: string;
}

const STATUS_STYLES = {
  pending: {
    textColor: 'var(--color-text-3)',
    backgroundColor: 'color-mix(in srgb, var(--color-text-4) 18%, transparent)',
  },
  running: {
    textColor: 'var(--color-primary)',
    backgroundColor: 'color-mix(in srgb, var(--color-primary) 12%, transparent)',
  },
  success: {
    textColor: 'var(--color-success)',
    backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
  },
  failed: {
    textColor: 'var(--color-error)',
    backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
  },
  cancelling: {
    textColor: 'var(--color-warning)',
    backgroundColor: 'color-mix(in srgb, var(--color-warning) 16%, transparent)',
  },
  cancelled: {
    textColor: 'var(--color-warning)',
    backgroundColor: 'color-mix(in srgb, var(--color-warning) 16%, transparent)',
  },
  interrupted: {
    textColor: 'var(--color-text-2)',
    backgroundColor: 'color-mix(in srgb, var(--color-fill-5) 24%, transparent)',
  },
} as const;

const normalizeStatus = (status?: string | null) => {
  const normalized = (status || 'pending').toLowerCase();

  if (['success', 'completed', 'finished'].includes(normalized)) {
    return 'success';
  }

  if (normalized === 'published') {
    return 'success';
  }

  if (['failed', 'fail', 'error', 'timeout'].includes(normalized)) {
    return 'failed';
  }

  if (['running', 'processing'].includes(normalized)) {
    return 'running';
  }

  if (['cancelling', 'canceling', 'interrupt_requested'].includes(normalized)) {
    return 'cancelling';
  }

  if (normalized === 'terminating') {
    return 'cancelling';
  }

  if (['cancelled', 'canceled', 'killed'].includes(normalized)) {
    return 'cancelled';
  }

  if (['interrupted', 'stopped'].includes(normalized)) {
    return 'interrupted';
  }

  if (normalized === 'archived') {
    return 'interrupted';
  }

  if (normalized === 'not_found') {
    return 'interrupted';
  }

  if (normalized === 'unknown') {
    return 'pending';
  }

  return 'pending';
};

const fallbackLabel = (status?: string | null) => {
  const normalized = normalizeStatus(status);

  switch (normalized) {
    case 'running':
      return 'Running';
    case 'success':
      return 'Completed';
    case 'failed':
      return 'Failed';
    case 'cancelling':
      return 'Cancelling';
    case 'cancelled':
      return 'Cancelled';
    case 'interrupted':
      return 'Interrupted';
    default:
      return 'Pending';
  }
};

const ExecutionStatusBadge: React.FC<ExecutionStatusBadgeProps> = ({
  status,
  label,
  className = '',
}) => {
  const normalized = normalizeStatus(status);
  const palette = STATUS_STYLES[normalized];

  return (
    <StatusBadgeShell
      className={className}
      label={label || fallbackLabel(status)}
      palette={palette}
    />
  );
};

export default ExecutionStatusBadge;
