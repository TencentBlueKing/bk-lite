import { describe, expect, it } from 'vitest';
import {
  applyScrollableEChartsTooltip,
  bindChartTooltipWheelScroll,
  ECHARTS_AXIS_TOOLTIP_MAX_HEIGHT_RATIO,
  ECHARTS_AXIS_TOOLTIP_MIN_HEIGHT_PX,
  ECHARTS_AXIS_TOOLTIP_SCROLL_ATTR,
  placeEChartsAxisTooltip,
  shouldForwardWheelToEChartsTooltip,
} from '@/components/echarts-tooltip-card';

function overflowingTooltip() {
  const tooltip = document.createElement('div');
  applyScrollableEChartsTooltip(tooltip, 400);
  Object.defineProperty(tooltip, 'scrollHeight', { configurable: true, value: 400 });
  Object.defineProperty(tooltip, 'clientHeight', { configurable: true, value: 150 });
  tooltip.scrollTop = 0;
  return tooltip;
}

describe('scrollable ECharts axis tooltip', () => {
  it('caps tooltip height to 60% of the chart and enables vertical scrolling', () => {
    const el = document.createElement('div');
    applyScrollableEChartsTooltip(el, 400);

    expect(el.style.maxHeight).toBe(`${Math.floor(400 * ECHARTS_AXIS_TOOLTIP_MAX_HEIGHT_RATIO)}px`);
    expect(el.style.overflowY).toBe('auto');
    expect(el.style.overscrollBehavior).toBe('contain');
    expect(el.getAttribute(ECHARTS_AXIS_TOOLTIP_SCROLL_ATTR)).toBe('scroll');
  });

  it('keeps a minimum height so tiny widgets still have a usable tooltip', () => {
    const el = document.createElement('div');
    applyScrollableEChartsTooltip(el, 80);
    expect(el.style.maxHeight).toBe(`${ECHARTS_AXIS_TOOLTIP_MIN_HEIGHT_PX}px`);
  });

  it('places the tooltip to the left when the right side overflows', () => {
    const el = document.createElement('div');
    const [x, y] = placeEChartsAxisTooltip(
      [500, 40],
      { contentSize: [180, 320], viewSize: [600, 300] },
      el,
      { x: 40, y: 10 },
    );

    expect(x).toBe(280);
    expect(y).toBe(10);
    expect(el.style.maxHeight).toBe('180px');
    expect(el.style.overflowY).toBe('auto');
  });

  it('forwards wheel from the chart canvas to the tooltip without moving onto it', () => {
    const root = document.createElement('div');
    const canvas = document.createElement('canvas');
    const tooltip = overflowingTooltip();
    root.append(canvas, tooltip);
    document.body.append(root);

    const unbind = bindChartTooltipWheelScroll(root);
    const event = new WheelEvent('wheel', { deltaY: 80, bubbles: true, cancelable: true });
    canvas.dispatchEvent(event);

    expect(tooltip.scrollTop).toBe(80);
    expect(event.defaultPrevented).toBe(true);
    unbind();
    root.remove();
  });

  it('does not double-scroll when the pointer is already over the tooltip', () => {
    const root = document.createElement('div');
    const tooltip = overflowingTooltip();
    root.append(tooltip);

    expect(shouldForwardWheelToEChartsTooltip({ target: tooltip }, root)).toBeNull();
    expect(shouldForwardWheelToEChartsTooltip({ target: document.createElement('canvas') }, root)).toBe(tooltip);
  });
});
