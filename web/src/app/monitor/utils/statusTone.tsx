import type { ReactNode } from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

export const STATUS_TONE = {
  success: {
    textColor: 'var(--color-success)',
    backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
  },
  warning: {
    textColor: 'var(--color-warning)',
    backgroundColor: 'color-mix(in srgb, var(--color-warning) 16%, transparent)',
  },
  fail: {
    textColor: 'var(--color-fail)',
    backgroundColor: 'color-mix(in srgb, var(--color-fail) 12%, transparent)',
  },
  primary: {
    textColor: 'var(--color-primary)',
    backgroundColor: 'color-mix(in srgb, var(--color-primary) 12%, transparent)',
  },
  neutral: {
    textColor: 'var(--color-text-2)',
    backgroundColor: 'color-mix(in srgb, var(--color-fill-5) 32%, transparent)',
  },
} as const;

export type StatusTone = keyof typeof STATUS_TONE;

export function StatusToneBadge({
  tone,
  label,
  className,
}: {
  tone: StatusTone;
  label: ReactNode;
  className?: string;
}) {
  return (
    <StatusBadgeShell
      label={label}
      palette={STATUS_TONE[tone]}
      className={className}
    />
  );
}
