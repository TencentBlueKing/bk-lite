import React from 'react';

export interface ChartAxisTickLabelProps {
  label: string;
  x: number;
  y: number;
  maxLength?: number;
  dx?: number;
  dy?: number;
  fontSize?: number;
  fill?: string;
  textAnchor?: 'start' | 'middle' | 'end' | 'inherit';
}

const ChartAxisTickLabel: React.FC<ChartAxisTickLabelProps> = ({
  label,
  x,
  y,
  maxLength = 6,
  dx = 0,
  dy = 4,
  fontSize = 14,
  fill = 'var(--color-text-3)',
  textAnchor = 'end',
}) => {
  const truncatedLabel =
    label.length > maxLength ? `${label.slice(0, maxLength - 1)}...` : label;

  return (
    <text
      x={x}
      y={y}
      dx={dx}
      dy={dy}
      textAnchor={textAnchor}
      fontSize={fontSize}
      fill={fill}
    >
      {label.length > maxLength ? <title>{label}</title> : null}
      {truncatedLabel}
    </text>
  );
};

export default ChartAxisTickLabel;
