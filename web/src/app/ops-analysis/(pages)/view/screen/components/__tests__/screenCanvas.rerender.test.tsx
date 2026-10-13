import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ScreenCanvas from '../screenCanvas';
import { createScreenWidgetItem } from '../../utils/layoutUtils';
import { createScreenDecorationItem, createScreenShapeItem } from '../../utils/screenItems';
import { buildDefaultScreenViewSets } from '../../utils/viewport';
import * as metrics from '../../utils/metrics';

const widgetRenderCounts = new Map<string, number>();

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('react-rnd', () => ({
  Rnd: ({
    children,
    style,
    ...rest
  }: {
    children: React.ReactNode;
    style?: React.CSSProperties;
    'data-screen-item-id'?: string;
  }) => (
    <div data-screen-item-id={rest['data-screen-item-id']} style={style}>
      {children}
    </div>
  ),
}));

vi.mock('../screenWidgetRenderer', () => ({
  default: ({ item, fitScale }: { item: { id: string }; fitScale?: number }) => {
    widgetRenderCounts.set(item.id, (widgetRenderCounts.get(item.id) ?? 0) + 1);
    return <div data-testid={`widget-${item.id}`} data-fit-scale={fitScale} />;
  },
}));

vi.mock('../screenChromeRenderer', () => ({
  default: () => null,
}));

vi.mock('../screenChromeSkins', () => ({
  ScreenChromeSkinStyles: () => null,
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverStub);
});

afterEach(() => {
  cleanup();
  widgetRenderCounts.clear();
});

describe('ScreenCanvas item updates', () => {
  it('does not rerender untouched widgets when one item appearance changes', () => {
    const base = buildDefaultScreenViewSets();
    const first = createScreenWidgetItem('single', []);
    const second = createScreenWidgetItem('gauge', [first]);
    const viewSets = { ...base, items: [first, second] };
    const view = render(
      <ScreenCanvas viewSets={viewSets} editMode selectedItemId={first.id} />,
    );

    const firstBefore = widgetRenderCounts.get(first.id) ?? 0;
    const secondBefore = widgetRenderCounts.get(second.id) ?? 0;
    expect(firstBefore).toBeGreaterThan(0);
    expect(secondBefore).toBeGreaterThan(0);

    const patched = {
      ...first,
      valueConfig: {
        ...first.valueConfig,
        appearance: { frame: 'panel' as const },
      },
    };
    view.rerender(
      <ScreenCanvas
        viewSets={{ ...viewSets, items: [patched, second] }}
        editMode
        selectedItemId={first.id}
      />,
    );

    expect(widgetRenderCounts.get(first.id)).toBeGreaterThan(firstBefore);
    expect(widgetRenderCounts.get(second.id)).toBe(secondBefore);
  });

  it('does not pin a selected item above its real zIndex', () => {
    const base = buildDefaultScreenViewSets();
    const first = createScreenWidgetItem('single', []);
    const viewSets = { ...base, items: [first] };
    render(
      <ScreenCanvas viewSets={viewSets} editMode selectedItemId={first.id} />,
    );

    const css = Array.from(document.querySelectorAll('style'))
      .map((node) => node.textContent ?? '')
      .join('\n');
    const selectedRule = css.match(/\.screen-rnd-node--selected\s*\{[^}]*\}/)?.[0] ?? '';
    expect(selectedRule).toContain('outline: 2px solid var(--color-primary)');
    expect(selectedRule).not.toMatch(/z-index|box-shadow/);
  });

  it('gives widgets the smaller fit scale when fill stretches the axes differently', () => {
    const spy = vi.spyOn(metrics, 'calculateScreenVisualMetrics').mockReturnValue({
      fitScale: 0.5,
      scaleX: 2,
      scaleY: 0.5,
      renderedWidth: 800,
      renderedHeight: 400,
      overflowX: false,
      overflowY: false,
      screenDensity: 1,
      screenUiScale: 2,
    });
    const base = buildDefaultScreenViewSets();
    const first = createScreenWidgetItem('single', []);
    const view = render(
      <ScreenCanvas
        viewSets={{ ...base, items: [first], viewport: { ...base.viewport, adapter: 'fill' } }}
        fullscreen
      />,
    );

    expect(view.getByTestId(`widget-${first.id}`).getAttribute('data-fit-scale')).toBe('0.5');
    spy.mockRestore();
  });

  it('lets decoration borders pass pointer events outside edit mode', () => {
    const base = buildDefaultScreenViewSets();
    const border = createScreenDecorationItem([], 'panelFrame', 'border-22');
    const shape = createScreenShapeItem([], 'rect');
    const viewSets = { ...base, items: [border, shape] };
    const view = render(<ScreenCanvas viewSets={viewSets} />);
    const borderSelector = `[data-screen-item-id="${border.id}"]`;
    const pointerEvents = (selector: string) =>
      (view.container.querySelector(selector) as HTMLElement | null)?.style.pointerEvents;

    expect(pointerEvents(borderSelector)).toBe('none');
    expect(pointerEvents(`[data-screen-item-id="${shape.id}"]`)).toBe('');

    view.rerender(<ScreenCanvas viewSets={viewSets} editMode />);
    expect(pointerEvents(borderSelector)).toBe('');

    view.rerender(<ScreenCanvas viewSets={viewSets} editMode fullscreen />);
    expect(pointerEvents(borderSelector)).toBe('none');
  });
});
