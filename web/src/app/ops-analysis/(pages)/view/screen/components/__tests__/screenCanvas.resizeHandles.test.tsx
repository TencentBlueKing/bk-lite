import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ScreenCanvas from '../screenCanvas';
import { createScreenTextItem } from '../../utils/screenItems';
import { buildDefaultScreenViewSets } from '../../utils/viewport';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('react-rnd', () => ({
  Rnd: ({
    children,
    enableResizing,
    resizeHandleClasses,
    style,
    ...rest
  }: {
    children: React.ReactNode;
    enableResizing?: Record<string, boolean>;
    resizeHandleClasses?: Record<string, string>;
    style?: React.CSSProperties;
    'data-screen-item-id'?: string;
  }) => (
    <div data-screen-item-id={rest['data-screen-item-id']} style={style}>
      {Object.entries(enableResizing ?? {}).map(([direction, enabled]) =>
        enabled ? (
          <span
            key={direction}
            data-resize-handle={direction}
            className={resizeHandleClasses?.[direction]}
          />
        ) : null,
      )}
      {children}
    </div>
  ),
}));

vi.mock('../screenWidgetRenderer', () => ({
  default: () => null,
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
});

const renderItem = (
  size: { w: number; h: number },
  props: Partial<React.ComponentProps<typeof ScreenCanvas>> = {},
) => {
  const base = buildDefaultScreenViewSets();
  const item = createScreenTextItem([], {
    id: 'title',
    content: '标题',
    x: 40,
    y: 40,
    ...size,
    zIndex: 1,
  });
  return render(
    <ScreenCanvas
      viewSets={{ ...base, items: [item] }}
      editMode
      selectedItemId={item.id}
      {...props}
    />,
  );
};

const handleDirections = (view: ReturnType<typeof render>) =>
  [...view.container.querySelectorAll('[data-resize-handle]')].map((node) =>
    node.getAttribute('data-resize-handle'),
  );

describe('ScreenCanvas resize handles', () => {
  it('renders eight handles with the existing corner classes when selected', () => {
    const view = renderItem({ w: 320, h: 180 });
    expect(handleDirections(view).sort()).toEqual(
      ['bottom', 'bottomLeft', 'bottomRight', 'left', 'right', 'top', 'topLeft', 'topRight'].sort(),
    );
    expect(view.container.querySelector('[data-resize-handle="top"]')?.className).toContain(
      'screen-rnd-handle--n',
    );
    expect(view.container.querySelector('[data-resize-handle="right"]')?.className).toContain(
      'screen-rnd-handle--e',
    );
    expect(view.container.querySelector('style')?.textContent).toContain('cursor: ns-resize');
    expect(view.container.querySelector('style')?.textContent).toContain('cursor: ew-resize');
  });

  it('hides every handle outside edit selection, preview, and when the component is small', () => {
    const idle = renderItem({ w: 320, h: 180 }, { selectedItemId: null });
    expect(handleDirections(idle)).toEqual([]);

    cleanup();
    const preview = renderItem({ w: 320, h: 180 }, { editMode: false });
    expect(handleDirections(preview)).toEqual([]);

    cleanup();
    const fullscreen = renderItem({ w: 320, h: 180 }, { fullscreen: true });
    expect(handleDirections(fullscreen)).toEqual([]);

    cleanup();
    const narrow = renderItem({ w: 36, h: 180 });
    expect(handleDirections(narrow).sort()).toEqual(
      ['bottomLeft', 'bottomRight', 'left', 'right', 'topLeft', 'topRight'].sort(),
    );

    cleanup();
    const tiny = renderItem({ w: 30, h: 20 });
    expect(handleDirections(tiny).sort()).toEqual(
      ['bottomLeft', 'bottomRight', 'topLeft', 'topRight'].sort(),
    );
  });
});
