import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

export interface VersionBadgeProps {
  value?: React.ReactNode;
  fallback?: React.ReactNode;
  className?: string;
}

const VersionBadge: React.FC<VersionBadgeProps> = ({
  value,
  fallback = 'v1.0.0',
  className = '',
}) => {
  const resolvedValue = value || fallback;

  return (
    <StatusBadgeShell
      label={resolvedValue}
      className={className}
      palette={{
        textColor: 'var(--color-primary)',
        backgroundColor:
          'color-mix(in srgb, var(--color-primary) 12%, transparent)',
      }}
    />
  );
};

export default VersionBadge;
