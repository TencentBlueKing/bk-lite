// @vitest-environment jsdom

import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ComTable from '@/app/ops-analysis/components/widgets/comTable';
import EventTable from '@/app/ops-analysis/components/widgets/eventTable/eventTable';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
  }),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
});

afterEach(() => {
  cleanup();
});

const dataSource = {
  params: [{ name: 'page' }, { name: 'page_size' }],
  field_schema: [{ key: 'name', title: '名称', value_type: 'string' }],
} as any;

const frameClass = (container: HTMLElement) => {
  const frame = container.querySelector<HTMLElement>('.pt-2');
  expect(frame).not.toBeNull();
  return frame as HTMLElement;
};

describe('table card pagination frame', () => {
  it('keeps the dashboard table gap inside the full-height box', () => {
    const view = render(
      <div style={{ width: 770, height: 519 }}>
        <ComTable
          rawData={{ items: [{ name: 'bare-01' }], count: 16 }}
          loading={false}
          dataSource={dataSource}
          config={{
            chartType: 'table',
            tableConfig: {
              columns: [{ key: 'name', title: '名称', visible: true, order: 0 }],
            },
          }}
        />
      </div>,
    );

    const frame = frameClass(view.container);
    expect(frame.className).toContain('h-full');
    expect(frame.className).toContain('min-h-0');
    expect(frame.className).toContain('pt-2');
    expect(frame.className).not.toContain('mt-2');
  });

  it('keeps the event table gap inside the measured body', () => {
    const view = render(
      <div style={{ width: 770, height: 519 }}>
        <EventTable
          rawData={{ items: [{ id: '1', summary: '告警' }], count: 4 }}
          loading={false}
          dataSource={dataSource}
          config={{
            chartType: 'eventTable',
            tableConfig: {
              columns: [{ key: 'summary', title: '摘要', visible: true, order: 0 }],
            },
          }}
        />
      </div>,
    );

    const frame = frameClass(view.container);
    expect(frame.className).toContain('pt-2');
    expect(frame.className).not.toContain('mt-2');
    const measured = frame.firstElementChild as HTMLElement | null;
    expect(measured?.className).toContain('overflow-hidden');
    expect(measured).not.toBe(frame);
  });

  it.each([
    { parentHeight: 226, scale: 1 },
    { parentHeight: 400, scale: 0.5 },
    { parentHeight: 400, scale: 2 },
  ])(
    'locks the table to the parent height $parentHeight at scale $scale',
    ({ parentHeight, scale }) => {
      const prototype = HTMLElement.prototype;
      const previousHeight = Object.getOwnPropertyDescriptor(prototype, 'clientHeight');
      const previousWidth = Object.getOwnPropertyDescriptor(prototype, 'clientWidth');
      Object.defineProperty(prototype, 'clientHeight', {
        configurable: true,
        get() {
          return parentHeight;
        },
      });
      Object.defineProperty(prototype, 'clientWidth', {
        configurable: true,
        get() {
          return 770;
        },
      });

      try {
        const view = render(
          <div style={{ width: 770, height: parentHeight + 40 }}>
            <ComTable
              rawData={{ items: [{ name: 'bare-01' }], count: 16 }}
              loading={false}
              dataSource={dataSource}
              screenRenderContext={{
                enabled: scale !== 1,
                fitScale: 1,
                screenDensity: scale,
                screenUiScale: scale,
                widgetDensity: scale,
                widgetUiScale: scale,
                layoutMode: 'viewportPixels',
              }}
              config={{
                chartType: 'table',
                chartThemeMode: scale === 1 ? 'default' : 'screen-dark',
                tableConfig: {
                  columns: [{ key: 'name', title: '名称', visible: true, order: 0 }],
                },
              }}
            />
          </div>,
        );

        const locked = view.container.querySelector<HTMLElement>('[class*="customTable"]');
        expect(locked).not.toBeNull();
        expect(locked?.style.height).toBe(`${parentHeight}px`);
        const bodyScroll = locked?.querySelector<HTMLElement>('.ant-table-body');
        expect(bodyScroll?.style.maxHeight || bodyScroll?.style.height).toBe(`${parentHeight - 47 - 56}px`);
      } finally {
        if (previousHeight) Object.defineProperty(prototype, 'clientHeight', previousHeight);
        else delete (prototype as { clientHeight?: number }).clientHeight;
        if (previousWidth) Object.defineProperty(prototype, 'clientWidth', previousWidth);
        else delete (prototype as { clientWidth?: number }).clientWidth;
      }
    },
  );

  it('locks the event table to the same parent height without the 160 floor', () => {
    const parentHeight = 226;
    const prototype = HTMLElement.prototype;
    const previousHeight = Object.getOwnPropertyDescriptor(prototype, 'clientHeight');
    const previousWidth = Object.getOwnPropertyDescriptor(prototype, 'clientWidth');
    Object.defineProperty(prototype, 'clientHeight', {
      configurable: true,
      get() {
        return parentHeight;
      },
    });
    Object.defineProperty(prototype, 'clientWidth', {
      configurable: true,
      get() {
        return 770;
      },
    });

    try {
      const view = render(
        <div style={{ width: 770, height: parentHeight + 40 }}>
          <EventTable
            rawData={{ items: [{ id: '1', summary: '告警' }], count: 16 }}
            loading={false}
            dataSource={dataSource}
            config={{
              chartType: 'eventTable',
              tableConfig: {
                columns: [{ key: 'summary', title: '摘要', visible: true, order: 0 }],
              },
            }}
          />
        </div>,
      );
      const locked = view.container.querySelector<HTMLElement>('[class*="customTable"]');
      expect(locked?.style.height).toBe(`${parentHeight}px`);
      const bodyScroll = locked?.querySelector<HTMLElement>('.ant-table-body');
      expect(bodyScroll?.style.maxHeight || bodyScroll?.style.height).toBe(`${parentHeight - 47 - 56}px`);
    } finally {
      if (previousHeight) Object.defineProperty(prototype, 'clientHeight', previousHeight);
      else delete (prototype as { clientHeight?: number }).clientHeight;
      if (previousWidth) Object.defineProperty(prototype, 'clientWidth', previousWidth);
      else delete (prototype as { clientWidth?: number }).clientWidth;
    }
  });
});
