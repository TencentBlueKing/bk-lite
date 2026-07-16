import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

interface EventStatusTagProps {
  label: React.ReactNode;
  active?: boolean;
}

const ACTIVE_COLORS = {
  text: 'var(--color-primary)',
  background: 'color-mix(in srgb, var(--color-primary) 12%, transparent)',
} as const;

const INACTIVE_COLORS = {
  text: 'var(--color-text-3)',
  background: 'color-mix(in srgb, var(--color-text-4) 18%, transparent)',
} as const;

const EventStatusTag: React.FC<EventStatusTagProps> = ({
  label,
  active = false,
}) => {
  const colors = active ? ACTIVE_COLORS : INACTIVE_COLORS;

  return (
    <StatusBadgeShell
      label={label}
      palette={{
        textColor: colors.text,
        backgroundColor: colors.background,
      }}
    />
  );
};

export default EventStatusTag;
