import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

export interface JobScriptTypeBadgeProps {
  scriptType?: string | null;
  label?: React.ReactNode;
  className?: string;
}

const SCRIPT_TYPE_STYLES = {
  shell: {
    textColor: 'var(--color-primary)',
    backgroundColor: 'color-mix(in srgb, var(--color-primary) 12%, transparent)',
  },
  python: {
    textColor: '#d46b08',
    backgroundColor: 'color-mix(in srgb, #d46b08 12%, transparent)',
  },
  bat: {
    textColor: 'var(--color-success)',
    backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
  },
  powershell: {
    textColor: '#722ed1',
    backgroundColor: 'color-mix(in srgb, #722ed1 12%, transparent)',
  },
} as const;

const SCRIPT_TYPE_LABELS: Record<string, string> = {
  shell: 'Shell',
  python: 'Python',
  bat: 'Bat',
  powershell: 'PowerShell',
};

const normalizeScriptType = (scriptType?: string | null) =>
  (scriptType || '').toLowerCase();

const JobScriptTypeBadge: React.FC<JobScriptTypeBadgeProps> = ({
  scriptType,
  label,
  className = '',
}) => {
  const normalized = normalizeScriptType(scriptType);
  const palette =
    SCRIPT_TYPE_STYLES[normalized as keyof typeof SCRIPT_TYPE_STYLES] || {
      textColor: 'var(--color-text-2)',
      backgroundColor:
        'color-mix(in srgb, var(--color-text-4) 14%, transparent)',
    };
  const resolvedLabel =
    label ||
    (normalized ? SCRIPT_TYPE_LABELS[normalized] || scriptType : '--');

  return (
    <StatusBadgeShell
      className={className}
      label={resolvedLabel}
      palette={palette}
    />
  );
};

export default JobScriptTypeBadge;
