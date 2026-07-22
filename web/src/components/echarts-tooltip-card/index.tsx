import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

export interface EChartsTooltipCardRow {
  key?: React.Key;
  color?: string;
  markerShape?: 'circle' | 'square' | 'none';
  label: React.ReactNode;
  value?: React.ReactNode;
}

export interface EChartsTooltipCardProps {
  title?: React.ReactNode;
  rows: EChartsTooltipCardRow[];
  minWidth?: number;
}

const containerStyle: React.CSSProperties = {
  minWidth: 148,
  borderRadius: 8,
  border: '1px solid var(--color-border-1)',
  background: 'var(--color-bg-1)',
  padding: '10px 12px',
  boxShadow: '0 8px 24px rgba(15, 23, 42, 0.08)',
  color: 'var(--color-text-1)',
};

const titleStyle: React.CSSProperties = {
  marginBottom: 6,
  color: 'var(--color-text-2)',
  fontSize: 12,
  fontWeight: 600,
  lineHeight: 1.4,
};

const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  fontSize: 12,
  lineHeight: 1.4,
};

const rowLabelStyle: React.CSSProperties = {
  flex: 1,
  color: 'var(--color-text-1)',
};

const rowValueStyle: React.CSSProperties = {
  color: 'var(--color-text-1)',
  fontWeight: 600,
  whiteSpace: 'nowrap',
};

const EChartsTooltipCard: React.FC<EChartsTooltipCardProps> = ({
  title,
  rows,
  minWidth,
}) => {
  return (
    <div
      style={{
        ...containerStyle,
        ...(minWidth ? { minWidth } : {}),
      }}
    >
      {title ? <div style={titleStyle}>{title}</div> : null}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {rows.map((row, index) => (
          <div key={row.key ?? index} style={rowStyle}>
            {row.markerShape !== 'none' ? (
              <span
                style={{
                  display: 'inline-block',
                  width: 10,
                  minWidth: 10,
                  height: 10,
                  borderRadius: row.markerShape === 'square' ? 2 : '50%',
                  backgroundColor: row.color || 'var(--color-primary)',
                }}
              />
            ) : null}
            <span style={rowLabelStyle}>{row.label}</span>
            {row.value !== undefined && row.value !== null ? (
              <span style={rowValueStyle}>{row.value}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
};

export const renderEChartsTooltipCard = (
  props: EChartsTooltipCardProps
) => renderToStaticMarkup(<EChartsTooltipCard {...props} />);

export default EChartsTooltipCard;
