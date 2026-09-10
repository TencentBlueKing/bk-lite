import React, { useCallback, useEffect, useRef } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

export const ECHARTS_AXIS_TOOLTIP_MAX_HEIGHT_RATIO = 0.6;
export const ECHARTS_AXIS_TOOLTIP_MIN_HEIGHT_PX = 96;
export const ECHARTS_AXIS_TOOLTIP_SCROLL_ATTR = 'data-echarts-axis-tooltip';

export interface EChartsAxisTooltipSize {
  contentSize: number[];
  viewSize: number[];
}

export interface EChartsAxisTooltipOffset {
  x?: number;
  y?: number;
}

export function applyScrollableEChartsTooltip(
  el: HTMLElement | null | undefined,
  viewHeight: number,
): void {
  if (!el) {
    return;
  }

  const maxHeight = Math.max(
    ECHARTS_AXIS_TOOLTIP_MIN_HEIGHT_PX,
    Math.floor(viewHeight * ECHARTS_AXIS_TOOLTIP_MAX_HEIGHT_RATIO),
  );
  el.style.maxHeight = `${maxHeight}px`;
  el.style.overflowY = 'auto';
  el.style.overscrollBehavior = 'contain';
  el.setAttribute(ECHARTS_AXIS_TOOLTIP_SCROLL_ATTR, 'scroll');
}

export function findScrollableEChartsTooltip(root: ParentNode): HTMLElement | null {
  return root.querySelector(`[${ECHARTS_AXIS_TOOLTIP_SCROLL_ATTR}="scroll"]`);
}

export function resolveWheelDeltaY(event: Pick<WheelEvent, 'deltaY' | 'deltaMode'>): number {
  return event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
}

export function shouldForwardWheelToEChartsTooltip(
  event: Pick<WheelEvent, 'target'>,
  root: ParentNode,
): HTMLElement | null {
  const tooltip = findScrollableEChartsTooltip(root);
  if (!tooltip) {
    return null;
  }
  if (event.target instanceof Node && tooltip.contains(event.target)) {
    return null;
  }
  if (tooltip.scrollHeight <= tooltip.clientHeight + 1) {
    return null;
  }
  return tooltip;
}

export function bindChartTooltipWheelScroll(root: HTMLElement): () => void {
  const onWheel = (event: WheelEvent) => {
    const tooltip = shouldForwardWheelToEChartsTooltip(event, root);
    if (!tooltip) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    tooltip.scrollTop += resolveWheelDeltaY(event);
  };

  root.addEventListener('wheel', onWheel, { capture: true, passive: false });
  return () => {
    root.removeEventListener('wheel', onWheel, { capture: true });
  };
}

export function useChartTooltipWheelScrollRef() {
  const unbindRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      unbindRef.current?.();
      unbindRef.current = null;
    };
  }, []);

  return useCallback((node: HTMLElement | null) => {
    unbindRef.current?.();
    unbindRef.current = node ? bindChartTooltipWheelScroll(node) : null;
  }, []);
}

export function placeEChartsAxisTooltip(
  point: number[],
  size: EChartsAxisTooltipSize,
  el?: HTMLElement | null,
  offset?: EChartsAxisTooltipOffset,
): [number, number] {
  applyScrollableEChartsTooltip(el, size.viewSize[1] || 0);
  const offsetX = offset?.x ?? 40;
  const offsetY = offset?.y ?? 10;
  const tooltipWidth = size.contentSize[0];
  const chartWidth = size.viewSize[0];
  let x = point[0] + offsetX;
  if (x + tooltipWidth > chartWidth) {
    x = Math.max(0, point[0] - tooltipWidth - offsetX);
  }
  return [x, offsetY];
}

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
  position: 'sticky',
  top: 0,
  zIndex: 1,
  marginBottom: 6,
  background: 'var(--color-bg-1)',
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
