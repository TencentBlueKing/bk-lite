import React from 'react';
import { Tooltip } from 'antd';

import SummaryMetricCard from '@/components/summary-metric-card';

export interface KpiCardProps {
  label: string;
  value: string | number;
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
  icon: React.ReactNode;
  exactValue?: string;
  maxFontSize: number;
}

const KPI_TONE_STYLES = {
  neutral: {
    iconColor: 'var(--color-primary)',
    iconBackground: 'color-mix(in srgb, var(--color-primary) 10%, transparent)',
    valueColor: 'var(--color-text-1)',
  },
  success: {
    iconColor: 'var(--color-success)',
    iconBackground: 'color-mix(in srgb, var(--color-success) 10%, transparent)',
    valueColor: 'var(--color-success)',
  },
  warning: {
    iconColor: 'var(--theme-color-status-warning)',
    iconBackground: 'color-mix(in srgb, var(--theme-color-status-warning) 12%, transparent)',
    valueColor: 'var(--theme-color-status-warning)',
  },
  danger: {
    iconColor: 'var(--color-fail)',
    iconBackground: 'color-mix(in srgb, var(--color-fail) 10%, transparent)',
    valueColor: 'var(--color-fail)',
  },
} as const;

export default function KpiCard({
  label,
  value,
  tone = 'neutral',
  icon,
  exactValue,
  maxFontSize,
}: KpiCardProps) {
  const toneStyle = KPI_TONE_STYLES[tone];

  return (
    <Tooltip title={exactValue ? `${label}: ${exactValue}` : undefined}>
      <SummaryMetricCard
        icon={icon}
        iconBackground={toneStyle.iconBackground}
        iconColor={toneStyle.iconColor}
        label={label}
        value={value}
        valueColor={toneStyle.valueColor}
        className="h-full min-h-[88px] min-w-0 px-4 py-3 transition-colors duration-200 hover:border-[var(--color-border-2)]"
        iconClassName="h-10 w-10 rounded-[10px] text-[18px]"
        contentClassName="flex-1"
        labelClassName="font-medium text-[var(--color-text-2)]"
        valueClassName="tracking-tight"
        valueRowClassName="[&>*:first-child]:flex-1"
        minFontSize={14}
        maxFontSize={maxFontSize}
      />
    </Tooltip>
  );
}
