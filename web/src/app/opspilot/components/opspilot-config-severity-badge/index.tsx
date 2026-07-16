import React from 'react';
import StatusBadgeShell from '@/components/status-badge-shell';

export type OpspilotConfigSeverity =
  | 'critical'
  | 'high'
  | 'medium'
  | 'low'
  | 'warning'
  | 'info'
  | 'unknown';

export interface OpspilotConfigSeverityBadgeProps {
  severity: OpspilotConfigSeverity;
  label?: React.ReactNode;
  className?: string;
}

const SEVERITY_STYLES: Record<
  OpspilotConfigSeverity,
  { textColor: string; backgroundColor: string; label: string }
> = {
  critical: {
    textColor: '#be123c',
    backgroundColor: 'rgba(244, 63, 94, 0.12)',
    label: '严重',
  },
  high: {
    textColor: '#c2410c',
    backgroundColor: 'rgba(249, 115, 22, 0.12)',
    label: '高危',
  },
  medium: {
    textColor: '#b45309',
    backgroundColor: 'rgba(245, 158, 11, 0.12)',
    label: '中风险',
  },
  low: {
    textColor: '#4d7c0f',
    backgroundColor: 'rgba(132, 204, 22, 0.12)',
    label: '低风险',
  },
  warning: {
    textColor: 'var(--color-warning)',
    backgroundColor:
      'color-mix(in srgb, var(--color-warning) 12%, transparent)',
    label: '警告',
  },
  info: {
    textColor: 'var(--color-primary)',
    backgroundColor:
      'color-mix(in srgb, var(--color-primary) 12%, transparent)',
    label: '提示',
  },
  unknown: {
    textColor: 'var(--color-text-2)',
    backgroundColor:
      'color-mix(in srgb, var(--color-fill-5) 32%, transparent)',
    label: '未识别',
  },
};

const OpspilotConfigSeverityBadge: React.FC<
  OpspilotConfigSeverityBadgeProps
> = ({ severity, label, className = '' }) => {
  const palette = SEVERITY_STYLES[severity] || SEVERITY_STYLES.unknown;

  return (
    <StatusBadgeShell
      label={label || palette.label}
      className={className}
      palette={palette}
    />
  );
};

export default OpspilotConfigSeverityBadge;
