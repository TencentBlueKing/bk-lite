import type { ReactNode } from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

export interface OpspilotAvailabilityBadgeProps {
  online?: boolean;
  label?: ReactNode;
  className?: string;
}

const OpspilotAvailabilityBadge = ({
  online = false,
  label,
  className = '',
}: OpspilotAvailabilityBadgeProps) => {
  const textColor = online ? 'var(--color-success)' : 'var(--color-text-3)';
  const backgroundColor = online
    ? 'color-mix(in srgb, var(--color-success) 12%, transparent)'
    : 'color-mix(in srgb, var(--color-text-4) 18%, transparent)';
  const dotColor = online ? '#389e0d' : '#cdcdcd';

  return (
    <StatusBadgeShell
      className={className}
      label={(
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: dotColor }}
          />
          <span>{label || (online ? 'Online' : 'Offline')}</span>
        </span>
      )}
      palette={{ textColor, backgroundColor }}
    />
  );
};

export default OpspilotAvailabilityBadge;
