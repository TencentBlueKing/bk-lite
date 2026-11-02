import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render } from '@testing-library/react';
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
    default: defaults,
    size,
    scale,
    ...rest
  }: {
    children: React.ReactNode;
    style?: React.CSSProperties;
    default?: { x: number; y: number; width: number; height: number };
    size?: { width: number; height: number };
    scale?: number;
    'data-screen-item-id'?: string;
  }) => (
    <div
      data-screen-item-id={rest['data-screen-item-id']}
      data-x={defaults?.x}
      data-y={defaults?.y}
      data-w={size?.width ?? defaults?.width}
      data-h={size?.height ?? defaults?.height}
      data-rnd-scale={scale}
      style={style}
    >
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
  ChromeFontDensityProvider: ({ children }: { children: React.ReactNode }) => children,
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

describe('ScreenCanvas outside click', () => {
  const renderCanvas = (props: Partial<React.ComponentProps<typeof ScreenCanvas>> = {}) => {
    const onSelectItem = vi.fn();
    const onDismissInspector = vi.fn();
    const view = render(
      <ScreenCanvas
        viewSets={buildDefaultScreenViewSets()}
        editMode
        onSelectItem={onSelectItem}
        onDismissInspector={onDismissInspector}
        {...props}
      />,
    );
    const workbench = view.container.querySelector('.screen-canvas-workbench');
    const canvas = view.container.querySelector('.screen-tech-canvas');
    if (!workbench || !canvas) {
      throw new Error('canvas workbench was not rendered');
    }
    return { onSelectItem, onDismissInspector, workbench, canvas };
  };

  it('collapses the inspector from the margin and keeps a canvas click on canvas settings', () => {
    const { onSelectItem, onDismissInspector, workbench, canvas } = renderCanvas();

    fireEvent.click(workbench);
    expect(onDismissInspector).toHaveBeenCalledTimes(1);
    expect(onSelectItem).not.toHaveBeenCalled();

    fireEvent.click(canvas);
    expect(onSelectItem).toHaveBeenCalledWith(null);
    expect(onDismissInspector).toHaveBeenCalledTimes(1);
  });

  it('ignores a drag that ends on the workbench margin', () => {
    const { onDismissInspector, workbench } = renderCanvas();

    fireEvent.pointerDown(workbench, { button: 0, clientX: 10, clientY: 10 });
    fireEvent.click(workbench, { clientX: 40, clientY: 10 });

    expect(onDismissInspector).not.toHaveBeenCalled();
  });

  it('does not dismiss outside edit mode or while presenting fullscreen', () => {
    const preview = renderCanvas({ editMode: false });
    fireEvent.click(preview.workbench);
    expect(preview.onDismissInspector).not.toHaveBeenCalled();

    const fullscreen = renderCanvas({ fullscreen: true });
    fireEvent.click(fullscreen.workbench);
    expect(fullscreen.onDismissInspector).not.toHaveBeenCalled();
  });
});

describe('ScreenCanvas fill viewport pixels', () => {
  const mockWorkbenchSize = (width: number, height: number) =>
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const box = this.classList?.contains('screen-canvas-workbench')
        ? { width, height }
        : { width: 0, height: 0 };
      return {
        x: 0,
        y: 0,
        top: 0,
        left: 0,
        right: box.width,
        bottom: box.height,
        width: box.width,
        height: box.height,
        toJSON() {
          return {};
        },
      } as DOMRect;
    });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderSized = (
    props: Partial<React.ComponentProps<typeof ScreenCanvas>> = {},
    size = { width: 1920, height: 1200 },
  ) => {
    mockWorkbenchSize(size.width, size.height);
    const base = buildDefaultScreenViewSets();
    const widget = {
      ...createScreenWidgetItem('single', []),
      x: 10,
      y: 10,
      w: 30,
      h: 20,
    };
    const onMoveItem = vi.fn();
    const view = render(
      <ScreenCanvas
        viewSets={{
          ...base,
          items: [widget],
          viewport: { ...base.viewport, adapter: 'fill' },
        }}
        onMoveItem={onMoveItem}
        {...props}
      />,
    );
    const canvas = view.container.querySelector('.screen-tech-canvas') as HTMLElement;
    const node = view.container.querySelector(
      `[data-screen-item-id="${widget.id}"]`,
    ) as HTMLElement;
    return { view, canvas, node, widget, onMoveItem };
  };

  it.each([
    ['fullscreen', { fullscreen: true }],
    ['fullscreen from edit', { fullscreen: true, editMode: true }],
    ['share', { shareMode: true }],
  ] as const)('lays %s fill out in viewport pixels without a scale transform', (_label, props) => {
    const { canvas, node, widget, onMoveItem } = renderSized(props);

    expect(canvas.style.transform).toBe('none');
    expect(canvas.style.width).toBe('1920px');
    expect(canvas.style.height).toBe('1200px');
    expect(canvas.className).not.toContain('screen-tech-canvas--stretched');
    expect(node.dataset.x).toBe('10');
    expect(node.dataset.y).toBe('11');
    expect(node.dataset.w).toBe('30');
    expect(node.dataset.h).toBe('22');
    expect(node.dataset.rndScale).toBe('1');
    expect(widget).toMatchObject({ x: 10, y: 10, w: 30, h: 20 });
    expect(onMoveItem).not.toHaveBeenCalled();
  });

  it('keeps edit, plain view, and forced contain on the design transform', () => {
    const edit = renderSized({ editMode: true });
    expect(edit.canvas.style.transform.startsWith('scale(')).toBe(true);
    expect(edit.canvas.style.width).toBe('1920px');
    expect(edit.node.dataset.x).toBe('10');
    expect(edit.node.dataset.y).toBe('10');
    expect(edit.node.dataset.h).toBe('20');

    const view = renderSized({});
    expect(view.canvas.style.transform.startsWith('scale(')).toBe(true);
    expect(view.node.dataset.y).toBe('10');

    const pdf = renderSized({ fullscreen: true, forceContain: true });
    expect(pdf.canvas.style.transform.startsWith('scale(')).toBe(true);
    expect(pdf.canvas.style.width).toBe('1920px');
    expect(pdf.canvas.style.height).toBe('1080px');
    expect(pdf.node.dataset.y).toBe('10');
    expect(pdf.node.dataset.h).toBe('20');
  });

  it.each([
    ['fitWidth', 'fitWidth', { width: 2560, height: 1080 }],
    ['fitHeight', 'fitHeight', { width: 1920, height: 1400 }],
  ] as const)('keeps fullscreen %s on the uniform transform', (_label, adapter, size) => {
    const base = buildDefaultScreenViewSets();
    mockWorkbenchSize(size.width, size.height);
    const widget = {
      ...createScreenWidgetItem('single', []),
      x: 10,
      y: 10,
      w: 30,
      h: 20,
    };
    const view = render(
      <ScreenCanvas
        fullscreen
        viewSets={{
          ...base,
          items: [widget],
          viewport: { ...base.viewport, adapter },
        }}
      />,
    );
    const canvas = view.container.querySelector('.screen-tech-canvas') as HTMLElement;
    const node = view.container.querySelector(
      `[data-screen-item-id="${widget.id}"]`,
    ) as HTMLElement;

    expect(canvas.style.transform.startsWith('scale(')).toBe(true);
    expect(canvas.style.width).toBe('1920px');
    expect(canvas.style.height).toBe('1080px');
    expect(node.dataset.x).toBe('10');
    expect(node.dataset.y).toBe('10');
    expect(node.dataset.h).toBe('20');
    expect(node.dataset.rndScale).not.toBe('1');
  });
});
