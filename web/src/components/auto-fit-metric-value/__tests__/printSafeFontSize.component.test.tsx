// @vitest-environment jsdom

import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import AutoFitMetricValue from '@/components/auto-fit-metric-value';
import { buildPrintSafeFontSize } from '@/components/auto-fit-metric-value/printSafeFontSize';

const CARD_WIDTH = 348;
const TEXT_WIDTH = 348;

beforeAll(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  );
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
  vi.stubGlobal('cancelAnimationFrame', () => undefined);

  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() {
      return CARD_WIDTH;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get() {
      return 160;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'scrollWidth', {
    configurable: true,
    get() {
      return TEXT_WIDTH;
    },
  });
});

afterEach(cleanup);

describe('AutoFitMetricValue print-safe font', () => {
  it('keeps a CSS width cap so print reflow can shrink the height-fitted px', () => {
    render(
      <AutoFitMetricValue
        main="-13.4"
        unit="%"
        resolveFontSize={() => 80}
      />,
    );

    const visible = document.querySelector<HTMLElement>(
      '.inline-flex.max-w-full.whitespace-nowrap',
    );
    expect(visible).not.toBeNull();
    expect(visible!.style.fontSize).toBe(buildPrintSafeFontSize(80, TEXT_WIDTH));
    expect(visible!.parentElement?.style.containerType).toBe('inline-size');
  });
});
