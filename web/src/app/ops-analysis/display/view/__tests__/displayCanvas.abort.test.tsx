// @vitest-environment jsdom

import React, { StrictMode } from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ScreenDisplayViewPage from '@/app/ops-analysis/display/view/page';

const getDisplayCanvas = vi.hoisted(() => vi.fn());

vi.mock('@/app/ops-analysis/(pages)/view/screen', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/api/screenDisplay', () => ({
  useScreenDisplayApi: () => ({
    getDisplayCanvas,
    queryDisplayDataSource: vi.fn(),
    resolveDisplayOptionSource: vi.fn(),
    getDisplayDataSources: vi.fn(),
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/context/locale', () => ({
  useLocaleFromSearch: () => undefined,
}));

afterEach(() => {
  cleanup();
  getDisplayCanvas.mockReset();
});

describe('screen display bootstrap', () => {
  it('aborts the display canvas read on unmount and does not mark the page invalid', async () => {
    getDisplayCanvas.mockImplementation(() => new Promise(() => undefined));
    const view = render(
      <StrictMode>
        <ScreenDisplayViewPage />
      </StrictMode>,
    );
    await vi.waitFor(() => expect(getDisplayCanvas).toHaveBeenCalled());
    const live = getDisplayCanvas.mock.calls
      .map((call) => call[0] as AbortSignal)
      .filter((signal) => !signal.aborted);
    expect(live.length).toBeGreaterThan(0);
    view.unmount();
    expect(live.every((signal) => signal.aborted)).toBe(true);
    expect(document.body.textContent).not.toContain('获取数据失败');
  });
});
