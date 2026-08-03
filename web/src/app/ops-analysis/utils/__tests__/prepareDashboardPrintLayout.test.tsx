import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  DASHBOARD_PREPARE_PRINT_EVENT,
  prepareDashboardPrintLayout,
} from '@/app/ops-analysis/utils/prepareDashboardPrintLayout';

describe('prepareDashboardPrintLayout', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    document.documentElement.removeAttribute('style');
    document.body.removeAttribute('style');
  });

  it('emits prepare-print then expands overflow and fixed height containers', async () => {
    const phases: string[] = [];
    const onPrepare = (event: Event) => {
      phases.push((event as CustomEvent).detail.phase);
    };
    window.addEventListener(DASHBOARD_PREPARE_PRINT_EVENT, onPrepare);

    document.body.innerHTML = `
      <main style="height: 100vh; overflow: hidden;">
        <div data-dashboard-render-root="true"
             style="position: fixed; inset: 0; height: 100vh; overflow: auto;">
          <div data-export-expand="true" style="height: 100%; overflow: auto;">
            <div class="grid-stack" style="height: 900px; overflow: hidden;">
              <div>widget</div>
            </div>
          </div>
          <div data-export-hidden="true">toolbar</div>
        </div>
      </main>
    `;

    const root = document.querySelector<HTMLElement>(
      '[data-dashboard-render-root="true"]',
    );
    await prepareDashboardPrintLayout(root);

    expect(phases).toEqual(['prepare-print']);
    expect(root?.style.overflow).toBe('visible');
    expect(root?.style.height).toBe('auto');
    expect(root?.style.position).toBe('relative');

    const expand = document.querySelector<HTMLElement>(
      '[data-export-expand="true"]',
    );
    expect(expand?.style.overflow).toBe('visible');
    expect(expand?.style.height).toBe('auto');

    const grid = document.querySelector<HTMLElement>('.grid-stack');
    expect(grid?.style.overflow).toBe('visible');
    expect(grid?.style.height).toBe('auto');

    const hidden = document.querySelector<HTMLElement>(
      '[data-export-hidden="true"]',
    );
    expect(hidden?.style.display).toBe('none');

    const main = document.querySelector('main');
    expect(main?.style.overflow).toBe('visible');
    expect(main?.style.height).toBe('auto');

    window.removeEventListener(DASHBOARD_PREPARE_PRINT_EVENT, onPrepare);
  });

  it('keeps report-ready ordering: prepare-print happens before caller emits ready', async () => {
    const order: string[] = [];
    window.addEventListener(DASHBOARD_PREPARE_PRINT_EVENT, () => {
      order.push('prepare-print');
    });

    document.body.innerHTML = `
      <div data-dashboard-render-root="true" style="height: 100vh; overflow: auto;">
        <div data-export-expand="true" style="height: 100%; overflow: auto;"></div>
      </div>
    `;

    await prepareDashboardPrintLayout();
    order.push('report-ready');

    expect(order).toEqual(['prepare-print', 'report-ready']);
  });

  it('fails clearly when render root is missing', async () => {
    await expect(prepareDashboardPrintLayout(null)).rejects.toThrow(
      'Dashboard render root not found',
    );
  });
});
