import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

export interface JobTriggerSourceBadgeProps {
  source?: string | null;
  label?: React.ReactNode;
  className?: string;
}

const SOURCE_STYLES = {
  manual: {
    textColor: 'var(--color-primary)',
    backgroundColor: 'color-mix(in srgb, var(--color-primary) 12%, transparent)',
  },
  scheduled: {
    textColor: 'var(--color-warning)',
    backgroundColor: 'color-mix(in srgb, var(--color-warning) 14%, transparent)',
  },
  api: {
    textColor: '#722ed1',
    backgroundColor: 'color-mix(in srgb, #722ed1 12%, transparent)',
  },
} as const;

const normalizeSource = (source?: string | null) => {
  const normalized = (source || 'manual').toLowerCase();
  if (normalized in SOURCE_STYLES) {
    return normalized as keyof typeof SOURCE_STYLES;
  }
  return 'manual';
};

const fallbackLabel = (source?: string | null) => {
  const normalized = normalizeSource(source);
  if (normalized === 'scheduled') {
    return 'Scheduled';
  }
  if (normalized === 'api') {
    return 'API';
  }
  return 'Manual';
};

const JobTriggerSourceBadge: React.FC<JobTriggerSourceBadgeProps> = ({
  source,
  label,
  className = '',
}) => {
  const normalized = normalizeSource(source);
  const palette = SOURCE_STYLES[normalized];

  return (
    <StatusBadgeShell
      className={className}
      label={label || fallbackLabel(source)}
      palette={palette}
    />
  );
};

export default JobTriggerSourceBadge;
