import React from 'react';
import AutoFitMetricValue from '@/components/auto-fit-metric-value';

export interface SummaryMetricCardProps {
  icon?: React.ReactNode;
  iconBackground?: string;
  iconColor?: string;
  label: React.ReactNode;
  value: React.ReactNode;
  unit?: React.ReactNode;
  valueAside?: React.ReactNode;
  subtitle?: React.ReactNode;
  subtitleColor?: string;
  valueColor?: string;
  headerExtra?: React.ReactNode;
  footer?: React.ReactNode;
  layout?: 'horizontal' | 'vertical';
  framed?: boolean;
  headerSpacing?: 'default' | 'compact' | 'spacious';
  className?: string;
  headerClassName?: string;
  iconClassName?: string;
  contentClassName?: string;
  labelClassName?: string;
  valueClassName?: string;
  unitClassName?: string;
  valueRowClassName?: string;
  valueAsideClassName?: string;
  subtitleClassName?: string;
  footerClassName?: string;
  minFontSize?: number;
  maxFontSize?: number;
}

const SummaryMetricCard: React.FC<SummaryMetricCardProps> = ({
  icon,
  iconBackground,
  iconColor,
  label,
  value,
  unit,
  valueAside,
  subtitle,
  subtitleColor,
  valueColor = 'var(--color-text-1)',
  headerExtra,
  footer,
  layout = 'horizontal',
  framed = true,
  headerSpacing = 'default',
  className = '',
  headerClassName = '',
  iconClassName = '',
  contentClassName = '',
  labelClassName = '',
  valueClassName = '',
  unitClassName = '',
  valueRowClassName = '',
  valueAsideClassName = '',
  subtitleClassName = '',
  footerClassName = '',
  minFontSize = 20,
  maxFontSize = 30,
}) => {
  const verticalHeaderSpacingClassName =
    headerSpacing === 'compact'
      ? 'mb-1'
      : headerSpacing === 'spacious'
        ? 'mb-3.5'
        : '';

  if (layout === 'vertical') {
    return (
      <div
        className={`flex flex-col ${framed ? 'rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)]' : ''} ${className}`}
      >
        <div className={`flex items-center gap-2 ${verticalHeaderSpacingClassName} ${headerClassName}`}>
          {icon ? (
            <div
              className={`grid shrink-0 place-items-center rounded-[10px] text-[18px] ${iconClassName}`}
              style={{
                background: iconBackground,
                color: iconColor,
              }}
            >
              {icon}
            </div>
          ) : null}
          <div className={`truncate text-[13px] text-[var(--color-text-2)] ${labelClassName}`}>
            {label}
          </div>
          {headerExtra ? <div className="ml-auto shrink-0">{headerExtra}</div> : null}
        </div>
        <div className={`min-w-0 ${contentClassName}`}>
          <div className={`flex items-baseline gap-2.5 ${valueRowClassName}`}>
            <AutoFitMetricValue
              main={value}
              unit={unit}
              color={valueColor}
              unitColor="var(--color-text-3)"
              valueClassName={`font-bold tabular-nums ${valueClassName}`}
              unitClassName={`font-medium ${unitClassName}`}
              align="baseline"
              unitScale={0.5}
              gap={(fontSize) => Math.max(4, Math.round(fontSize * 0.08))}
              minFontSize={minFontSize}
              resolveFontSize={({ width, height }) => {
                const safeWidth = Math.max(width, 120);
                const safeHeight = Math.max(height, 32);
                return Math.max(
                  minFontSize,
                  Math.min(maxFontSize, safeWidth / 5.1, safeHeight * 0.78),
                );
              }}
            />
            {valueAside ? (
              <div className={`shrink-0 ${valueAsideClassName}`}>{valueAside}</div>
            ) : null}
          </div>
          {subtitle ? (
            <div
              className={`mt-2 text-xs text-[var(--color-text-3)] ${subtitleClassName}`}
              style={subtitleColor ? { color: subtitleColor } : undefined}
            >
              {subtitle}
            </div>
          ) : null}
        </div>
        {footer ? <div className={footerClassName}>{footer}</div> : null}
      </div>
    );
  }

  return (
    <div
      className={`flex items-center gap-4 ${framed ? 'rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)]' : ''} ${className}`}
    >
      {icon ? (
        <div
          className={`grid shrink-0 place-items-center rounded-full text-[22px] ${iconClassName}`}
          style={{
            background: iconBackground,
            color: iconColor,
          }}
        >
          {icon}
        </div>
      ) : null}
      <div className={`min-w-0 ${contentClassName}`}>
        <div className={`mb-1 truncate text-xs text-[var(--color-text-3)] ${labelClassName}`}>
          {label}
        </div>
        <div className={`flex items-baseline gap-2.5 ${valueRowClassName}`}>
          <AutoFitMetricValue
            main={value}
            unit={unit}
            color={valueColor}
            unitColor="var(--color-text-3)"
            valueClassName={`font-bold tabular-nums ${valueClassName}`}
            unitClassName={`font-medium ${unitClassName}`}
            align="baseline"
            unitScale={0.5}
            gap={(fontSize) => Math.max(4, Math.round(fontSize * 0.08))}
            minFontSize={minFontSize}
            resolveFontSize={({ width, height }) => {
              const safeWidth = Math.max(width, 120);
              const safeHeight = Math.max(height, 32);
              return Math.max(
                minFontSize,
                Math.min(maxFontSize, safeWidth / 5.1, safeHeight * 0.78),
              );
            }}
          />
          {valueAside ? (
            <div className={`shrink-0 ${valueAsideClassName}`}>{valueAside}</div>
          ) : null}
        </div>
        {subtitle ? (
          <div
            className={`mt-[3px] text-[11px] text-[var(--color-text-3)] ${subtitleClassName}`}
            style={subtitleColor ? { color: subtitleColor } : undefined}
          >
            {subtitle}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default SummaryMetricCard;
