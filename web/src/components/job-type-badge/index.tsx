import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

export interface JobTypeBadgeProps {
  type?: string | null;
  label?: React.ReactNode;
  className?: string;
}

const TYPE_STYLES = {
  script: {
    textColor: 'var(--color-primary)',
    backgroundColor: 'color-mix(in srgb, var(--color-primary) 12%, transparent)',
  },
  playbook: {
    textColor: '#722ed1',
    backgroundColor: 'color-mix(in srgb, #722ed1 12%, transparent)',
  },
  file: {
    textColor: 'var(--color-success)',
    backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
  },
} as const;

const normalizeType = (type?: string | null) => {
  const normalized = (type || 'script').toLowerCase();

  if (normalized === 'file_distribution') {
    return 'file';
  }

  if (normalized in TYPE_STYLES) {
    return normalized as keyof typeof TYPE_STYLES;
  }

  return 'script';
};

const fallbackLabel = (type?: string | null) => {
  const normalized = normalizeType(type);
  if (normalized === 'playbook') {
    return 'Playbook';
  }
  if (normalized === 'file') {
    return 'File';
  }
  return 'Script';
};

const JobTypeBadge: React.FC<JobTypeBadgeProps> = ({
  type,
  label,
  className = '',
}) => {
  const normalized = normalizeType(type);
  const palette = TYPE_STYLES[normalized];

  return (
    <StatusBadgeShell
      className={className}
      label={label || fallbackLabel(type)}
      palette={palette}
    />
  );
};

export default JobTypeBadge;
