import React from 'react';

interface EventLevelIndicatorProps {
  label: React.ReactNode;
  color: string;
}

const EventLevelIndicator: React.FC<EventLevelIndicatorProps> = ({
  label,
  color,
}) => {
  return (
    <div
      className="inline-flex items-center gap-2 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-3 py-1.5"
    >
      <span
        className="h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span style={{ color }}>{label}</span>
    </div>
  );
};

export default EventLevelIndicator;
