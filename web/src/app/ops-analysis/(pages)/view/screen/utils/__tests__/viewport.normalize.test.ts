import { describe, expect, it } from 'vitest';
import { isScreenClockItem, isScreenTitleFrameItem } from '../screenItems';
import {
  DEFAULT_SCREEN_VIEWPORT,
  normalizeScreenViewSets,
  resolveScreenDisplayAdapter,
  scaleScreenItemsToViewport,
  updateScreenViewport,
} from '../viewport';
import type { ScreenItem } from '@/app/ops-analysis/types/screen';

describe('normalizeScreenViewSets', () => {
  it('keeps a saved color background instead of resetting the default preset', () => {
    const normalized = normalizeScreenViewSets({
      viewport: {
        width: 1920,
        height: 1080,
        background: { type: 'color', color: '#112233' },
        adapter: 'fitWidth',
      },
      items: [],
      decorations: {},
    });

    expect(normalized.viewport.background).toEqual({
      type: 'color',
      color: '#112233',
    });
    expect(normalized.viewport.adapter).toBe('fitWidth');
  });

  it('defaults missing adapter to fill and fills a theme background', () => {
    const normalized = normalizeScreenViewSets({
      viewport: { width: 1366, height: 768 },
      items: [],
      decorations: {},
    });

    expect(normalized.viewport.adapter).toBe('fill');
    expect(normalized.viewport.background).toEqual(
      DEFAULT_SCREEN_VIEWPORT.background,
    );
  });

  it('migrates legacy title and clock chrome into canvas items once', () => {
    const normalized = normalizeScreenViewSets({
      viewport: { width: 1920, height: 1080 },
      items: [],
      decorations: {
        showTitle: true,
        showClock: true,
        title: '业务运行总览',
      },
    });

    expect(normalized.decorations.showTitle).toBe(false);
    expect(normalized.decorations.showClock).toBe(false);
    expect(normalized.items).toHaveLength(2);

    const title = normalized.items.find(isScreenTitleFrameItem);
    const clock = normalized.items.find(isScreenClockItem);
    expect(title?.content).toBe('业务运行总览');
    expect(title?.preset).toBe('hero-5');
    expect(title?.w).toBe(800);
    expect(title?.h).toBe(56);
    expect(title?.y).toBe(14);
    expect(title?.x).toBe(560);
    expect(title?.textStyle).toMatchObject({
      fontSize: 24,
      fontWeight: 800,
      align: 'center',
    });
    expect(clock?.format).toBe('YYYY-MM-DD HH:mm:ss');
    expect(clock?.w).toBe(300);
    expect(clock?.h).toBe(40);
    expect(clock?.y).toBe(18);
    expect(clock?.x).toBe(1526);
    expect(clock?.textStyle).toMatchObject({
      fontSize: 16,
      fontWeight: 700,
    });

    const again = normalizeScreenViewSets(normalized);
    expect(again.items).toHaveLength(2);
    expect(again.items.map((item) => item.id)).toEqual(
      normalized.items.map((item) => item.id),
    );
  });

  it('scales legacy chrome against larger design canvases', () => {
    const normalized = normalizeScreenViewSets({
      viewport: { width: 3840, height: 2160 },
      items: [],
      decorations: {
        showTitle: true,
        showClock: true,
        title: '告警运营大屏',
      },
    });

    const title = normalized.items.find(isScreenTitleFrameItem);
    const clock = normalized.items.find(isScreenClockItem);
    expect(title?.preset).toBe('hero-5');
    expect(title?.w).toBe(1600);
    expect(title?.h).toBe(112);
    expect(title?.textStyle?.fontSize).toBe(48);
    expect(clock?.w).toBe(600);
    expect(clock?.textStyle?.fontSize).toBe(32);
  });

  it('does not migrate an empty title switch into a title frame', () => {
    const normalized = normalizeScreenViewSets({
      viewport: { width: 1920, height: 1080 },
      items: [],
      decorations: { showTitle: true, title: '   ' },
    });

    expect(normalized.items.some(isScreenTitleFrameItem)).toBe(false);
    expect(normalized.decorations.showTitle).toBe(false);
  });
});

describe('resolveScreenDisplayAdapter', () => {
  it('uses the adapter only for enlarge and share', () => {
    expect(
      resolveScreenDisplayAdapter({
        adapter: 'fitHeight',
        editMode: false,
        fullscreen: false,
      }),
    ).toBe('contain');
    expect(
      resolveScreenDisplayAdapter({
        adapter: 'fitWidth',
        editMode: true,
        fullscreen: false,
      }),
    ).toBe('contain');
    expect(
      resolveScreenDisplayAdapter({
        adapter: 'fitHeight',
        fullscreen: true,
      }),
    ).toBe('fitHeight');
    expect(
      resolveScreenDisplayAdapter({
        adapter: 'fill',
        shareMode: true,
      }),
    ).toBe('fill');
    expect(
      resolveScreenDisplayAdapter({
        adapter: 'fitWidth',
        fullscreen: true,
        forceContain: true,
      }),
    ).toBe('contain');
  });
});

describe('scaleScreenItemsToViewport', () => {
  it('scales geometry with the canvas and keeps the same composition', () => {
    const items = [
      {
        id: 'card',
        type: 'widget',
        chartType: 'single',
        title: '主机',
        x: 960,
        y: 540,
        w: 480,
        h: 270,
        zIndex: 1,
        valueConfig: {},
      },
      {
        id: 'label',
        kind: 'text',
        content: '标题',
        x: 0,
        y: 0,
        w: 200,
        h: 40,
        zIndex: 2,
        textStyle: { fontSize: 20 },
      },
      {
        id: 'clock',
        kind: 'clock',
        format: 'HH:mm:ss',
        x: 400,
        y: 20,
        w: 200,
        h: 40,
        zIndex: 3,
        textStyle: { fontSize: 24, color: 'accent' },
      },
    ] as ScreenItem[];

    const scaled = scaleScreenItemsToViewport(items, 1920, 1080, 960, 540);

    expect(scaled[0]).toMatchObject({ x: 480, y: 270, w: 240, h: 135 });
    expect(scaled[1]).toMatchObject({
      x: 0,
      y: 0,
      w: 100,
      h: 20,
      textStyle: { fontSize: 10 },
    });
    expect(scaled[2]).toMatchObject({
      x: 200,
      y: 10,
      w: 100,
      h: 20,
      textStyle: { fontSize: 12, color: 'accent' },
    });
  });

  it('scales items when the viewport size changes', () => {
    const current = normalizeScreenViewSets({
      viewport: { width: 1920, height: 1080, adapter: 'fill' },
      items: [
        {
          id: 'card',
          type: 'widget',
          chartType: 'single',
          title: '主机',
          x: 100,
          y: 80,
          w: 200,
          h: 100,
          zIndex: 1,
          valueConfig: {},
        },
      ],
      decorations: {},
    });

    const next = updateScreenViewport(current, {
      ...current.viewport,
      width: 960,
      height: 540,
    });

    expect(next.items[0]).toMatchObject({ x: 50, y: 40, w: 100, h: 50 });
    expect(next.viewport.adapter).toBe('fill');
  });
});
