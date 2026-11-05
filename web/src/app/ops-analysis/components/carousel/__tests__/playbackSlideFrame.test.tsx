import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PlaybackSlide } from '@/app/ops-analysis/components/carousel/playbackCanvas';

const paint = vi.hoisted(() => ({
  dashboard: 0,
  dashboardMounts: 0,
  screenMounts: 0,
  explode: false,
}));

vi.mock('@/app/ops-analysis/(pages)/view/dashBoard', async () => {
  const React = await import('react');
  function DashboardCanvas() {
    if (paint.explode) {
      throw new Error('canvas boom');
    }
    paint.dashboard += 1;
    React.useEffect(() => {
      paint.dashboardMounts += 1;
    }, []);
    return <div data-testid="dashboard-canvas" />;
  }
  return { default: DashboardCanvas };
});

vi.mock('@/app/ops-analysis/(pages)/view/topology', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/(pages)/view/architecture', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/(pages)/view/screen', async () => {
  const React = await import('react');
  function ScreenCanvas() {
    React.useEffect(() => {
      paint.screenMounts += 1;
    }, []);
    return <div data-testid="screen-canvas" />;
  }
  return { default: ScreenCanvas };
});

vi.mock('@/app/ops-analysis/(pages)/view/report', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/(pages)/view/networkTopology', () => ({
  default: () => null,
}));

import { PlaybackSlideFrame } from '@/app/ops-analysis/components/carousel/playbackCanvas';

const slide: PlaybackSlide = {
  key: 's0',
  resourceType: 'dashboard',
  canvasId: 7,
  name: '机房总览',
  dwellSeconds: 30,
  available: true,
};

const onError = () => undefined;

describe('PlaybackSlideFrame', () => {
  it('keeps the canvas mounted when the parent repaints with the same slide inputs', () => {
    paint.dashboard = 0;
    paint.dashboardMounts = 0;
    const detail = { id: 7, name: '机房总览' };
    const view = render(
      <PlaybackSlideFrame
        slide={slide}
        initialDetail={detail}
        onError={onError}
        presentFullscreen={false}
      />,
    );
    expect(paint.dashboard).toBe(1);

    view.rerender(
      <PlaybackSlideFrame
        slide={{ ...slide }}
        initialDetail={detail}
        onError={onError}
        presentFullscreen={false}
      />,
    );
    expect(paint.dashboard).toBe(1);

    view.rerender(
      <PlaybackSlideFrame
        slide={{ ...slide }}
        initialDetail={{ id: 7, name: '新详情' }}
        onError={onError}
        presentFullscreen={false}
      />,
    );
    expect(paint.dashboard).toBe(2);
    expect(paint.dashboardMounts).toBe(1);
  });

  it('remounts the page when the canvas id changes and when the resource type changes', () => {
    paint.dashboardMounts = 0;
    paint.screenMounts = 0;
    const detail = { id: 7, name: '机房总览' };
    const view = render(
      <PlaybackSlideFrame
        slide={slide}
        initialDetail={detail}
        onError={onError}
      />,
    );
    expect(paint.dashboardMounts).toBe(1);

    view.rerender(
      <PlaybackSlideFrame
        slide={{ ...slide, canvasId: 8, key: 's1' }}
        initialDetail={{ id: 8, name: '下一盘' }}
        onError={onError}
      />,
    );
    expect(paint.dashboardMounts).toBe(2);
    expect(paint.screenMounts).toBe(0);

    view.rerender(
      <PlaybackSlideFrame
        slide={{ ...slide, resourceType: 'screen', canvasId: 3, key: 's2' }}
        initialDetail={{ id: 3 }}
        onError={onError}
      />,
    );
    expect(paint.screenMounts).toBe(1);
  });

  it('shows a spinner and reports the error when the canvas throws', () => {
    paint.explode = true;
    const onError = vi.fn();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const view = render(
      <PlaybackSlideFrame
        slide={slide}
        initialDetail={{ id: 7 }}
        onError={onError}
      />,
    );
    expect(onError).toHaveBeenCalledTimes(1);
    expect(view.container.querySelector('.ant-spin')).toBeTruthy();
    expect(view.container.querySelector('[data-testid="dashboard-canvas"]')).toBeNull();
    consoleError.mockRestore();
    paint.explode = false;
  });
});
