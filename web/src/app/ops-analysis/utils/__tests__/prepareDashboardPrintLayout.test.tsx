import { afterEach, describe, expect, it } from 'vitest';

import {
  DASHBOARD_PREPARE_PRINT_EVENT,
  prepareDashboardPrintLayout,
  prepareReportPrintLayout,
  prepareScreenPrintLayout,
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
    await expect(prepareReportPrintLayout(null)).rejects.toThrow(
      'Report render root not found',
    );
  });

  it('prepareReportPrintLayout expands overflow without touching grid-stack', async () => {
    document.body.innerHTML = `
      <div data-dashboard-render-root="true" style="height: 100vh; overflow: auto;">
        <div data-export-expand="true" style="height: 100%; overflow: auto;"></div>
        <div class="grid-stack" style="height: 900px; overflow: hidden;"></div>
      </div>
    `;

    const root = document.querySelector<HTMLElement>(
      '[data-dashboard-render-root="true"]',
    );
    await prepareReportPrintLayout(root);

    const grid = document.querySelector<HTMLElement>('.grid-stack');
    expect(grid?.style.overflow).not.toBe('visible');
    expect(grid?.style.height).not.toBe('auto');
  });

  it('prepareReportPrintLayout keeps untagged 420px cards and table scroll windows', async () => {
    document.body.innerHTML = `
      <div data-dashboard-render-root="true" style="min-height: 100vh; overflow: auto;">
        <div data-export-expand="true" style="height: 100%; overflow: auto;">
          <div id="report-card" style="height: 420px; overflow: hidden;">
            <div class="widget-scroll" style="height: 100%; overflow-y: auto;">
              <div class="ant-table-body" style="overflow: auto; max-height: 240px;"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    const root = document.querySelector<HTMLElement>(
      '[data-dashboard-render-root="true"]',
    );
    await prepareReportPrintLayout(root);

    const page = document.querySelector<HTMLElement>(
      '[data-export-expand="true"]',
    );
    expect(page?.style.height).toBe('auto');
    expect(page?.style.overflow).toBe('visible');

    const card = document.getElementById('report-card');
    expect(card?.style.height).toBe('420px');
    expect(card?.style.overflow).toBe('hidden');

    const tableBody = document.querySelector<HTMLElement>('.ant-table-body');
    expect(tableBody?.style.maxHeight).toBe('240px');
    expect(tableBody?.style.overflow).toBe('auto');
  });

  it('freezes WebGL canvases into images before Chromium print', async () => {
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.toDataURL = () =>
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
    HTMLCanvasElement.prototype.getContext = function (type: string, ...rest: unknown[]) {
      if (type === 'webgl' || type === 'webgl2') {
        return {} as RenderingContext;
      }
      return originalGetContext.call(this, type, ...rest as []);
    };

    try {
      document.body.innerHTML = `
        <div data-dashboard-render-root="true" style="width: 400px; height: 300px;">
          <div class="canvas">
            <canvas width="80" height="60" style="width: 80px; height: 60px;"></canvas>
          </div>
        </div>
      `;
      const canvas = document.querySelector('canvas');
      if (canvas) {
        canvas.width = 80;
        canvas.height = 60;
      }

      const root = document.querySelector<HTMLElement>(
        '[data-dashboard-render-root="true"]',
      );
      await prepareScreenPrintLayout(root);

      expect(root?.querySelector('canvas')).toBeNull();
      const image = root?.querySelector<HTMLImageElement>(
        'img[data-print-snapshot="true"]',
      );
      expect(image?.src).toMatch(/^data:image\/png/);
      expect(image?.style.width).toBe('80px');
      expect(image?.style.height).toBe('60px');
    } finally {
      HTMLCanvasElement.prototype.toDataURL = originalToDataURL;
      HTMLCanvasElement.prototype.getContext = originalGetContext;
    }
  });

  it('leaves 2D canvases in the DOM during print snapshot', async () => {
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type: string, ...rest: unknown[]) {
      if (type === '2d') {
        return {} as RenderingContext;
      }
      return originalGetContext.call(this, type, ...rest as []);
    };

    try {
      document.body.innerHTML = `
        <div data-dashboard-render-root="true">
          <canvas width="40" height="20"></canvas>
        </div>
      `;
      const canvas = document.querySelector('canvas');
      if (canvas) {
        canvas.width = 40;
        canvas.height = 20;
      }

      const root = document.querySelector<HTMLElement>(
        '[data-dashboard-render-root="true"]',
      );
      await prepareScreenPrintLayout(root);

      expect(root?.querySelector('canvas')).not.toBeNull();
      expect(root?.querySelector('img[data-print-snapshot="true"]')).toBeNull();
    } finally {
      HTMLCanvasElement.prototype.getContext = originalGetContext;
    }
  });

  it('prepareDashboardPrintLayout snapshots WebGL canvases then still expands overflow', async () => {
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.toDataURL = () =>
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
    HTMLCanvasElement.prototype.getContext = function (type: string, ...rest: unknown[]) {
      if (type === 'webgl' || type === 'webgl2') {
        return {} as RenderingContext;
      }
      return originalGetContext.call(this, type, ...rest as []);
    };

    try {
      document.body.innerHTML = `
        <div data-dashboard-render-root="true" style="height: 100vh; overflow: auto;">
          <canvas width="40" height="20"></canvas>
        </div>
      `;
      const canvas = document.querySelector('canvas');
      if (canvas) {
        canvas.width = 40;
        canvas.height = 20;
      }

      const root = document.querySelector<HTMLElement>(
        '[data-dashboard-render-root="true"]',
      );
      await prepareDashboardPrintLayout(root);

      expect(root?.querySelector('canvas')).toBeNull();
      expect(root?.querySelector('img[data-print-snapshot="true"]')).toBeTruthy();
      expect(root?.style.overflow).toBe('visible');
      expect(root?.style.height).toBe('auto');
    } finally {
      HTMLCanvasElement.prototype.toDataURL = originalToDataURL;
      HTMLCanvasElement.prototype.getContext = originalGetContext;
    }
  });
});
