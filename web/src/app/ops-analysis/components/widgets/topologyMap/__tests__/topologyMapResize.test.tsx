// @vitest-environment jsdom

import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const testState = vi.hoisted(() => ({
  graphs: [] as Array<{
    container: HTMLElement;
    width: number;
    height: number;
    fitCount: number;
    viewport: string;
  }>,
  resizeCallbacks: [] as ResizeObserverCallback[],
  translate: (key: string) => key,
}));

vi.mock('@antv/x6', () => {
  class FakeGraph {
    static registerNode() {}

    container: HTMLElement;
    width: number;
    height: number;
    fitCount = 0;
    viewport = 'initial';

    constructor(options: { container: HTMLElement; width: number; height: number }) {
      this.container = options.container;
      this.width = options.width;
      this.height = options.height;
      this.syncSizeAttribute();
      testState.graphs.push(this);
    }

    private syncSizeAttribute() {
      this.container.dataset.x6ViewportSize = `${this.width}x${this.height}`;
    }

    resize(width: number, height: number) {
      this.width = width;
      this.height = height;
      this.syncSizeAttribute();
    }

    zoomToFit() {
      this.fitCount += 1;
      this.viewport = 'fit';
      this.container.dataset.x6FitSize = `${this.width}x${this.height}`;
    }

    addNodes() {
      this.container.dataset.layoutReady = 'true';
    }

    addEdges() {}
    getCellById() { return undefined; }
    on() {}
    dispose() {}
  }

  return { Graph: FakeGraph };
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: testState.translate }),
}));

vi.mock('@ant-design/icons', () => ({
  CompressOutlined: () => <span aria-hidden="true" />,
}));

vi.mock('antd', () => ({
  Button: ({ onClick, 'aria-label': ariaLabel }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" aria-label={ariaLabel} onClick={onClick} />
  ),
  Empty: () => <div />,
  Spin: () => <div />,
  Tooltip: ({ children }: { children: React.ReactNode }) => children,
}));

import TopologyMap from '../index';

const payload = {
  nodes: [{
    id: 'node-a',
    instance_id: 1,
    instance_name: 'Node A',
    model_name: 'Host',
    alert_count: 0,
  }],
  edges: [],
};

const setElementSize = (element: Element, width: number, height: number) => {
  Object.defineProperties(element, {
    clientWidth: { configurable: true, get: () => width },
    clientHeight: { configurable: true, get: () => height },
  });
};

const triggerResize = () => {
  act(() => {
    testState.resizeCallbacks.forEach((callback) => {
      callback([], {} as ResizeObserver);
    });
  });
};

beforeEach(() => {
  testState.graphs.length = 0;
  testState.resizeCallbacks.length = 0;
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: ResizeObserverCallback) {
      testState.resizeCallbacks.push(callback);
    }
    observe() {}
    disconnect() {}
    unobserve() {}
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('TopologyMap live widget resize', () => {
  it('synchronizes X6 to the resized widget without waiting for a remount', async () => {
    const view = render(<TopologyMap rawData={payload} />);
    await waitFor(() => expect(testState.graphs).toHaveLength(1));
    const root = view.container.firstElementChild as HTMLElement;
    setElementSize(root, 640, 360);

    triggerResize();

    expect(testState.graphs[0].container.dataset.x6ViewportSize).toBe('640x360');
  });

  it('fits against the latest widget size even before ResizeObserver delivery', async () => {
    const view = render(<TopologyMap rawData={payload} />);
    await waitFor(() => expect(testState.graphs).toHaveLength(1));
    const root = view.container.firstElementChild as HTMLElement;
    setElementSize(root, 720, 420);

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.topologyMapFit' }));

    expect(testState.graphs[0].container.dataset.x6FitSize).toBe('720x420');
  });

  it('uses the latest continuous resize and preserves user viewport until explicit fit', async () => {
    const view = render(<TopologyMap rawData={payload} />);
    await waitFor(() => expect(testState.graphs).toHaveLength(1));
    const graph = testState.graphs[0];
    const root = view.container.firstElementChild as HTMLElement;
    graph.viewport = 'user-zoom-pan';
    const fitCountBeforeResize = graph.fitCount;

    setElementSize(root, 500, 300);
    triggerResize();
    setElementSize(root, 780, 460);
    triggerResize();

    expect(graph.container.dataset.x6ViewportSize).toBe('780x460');
    expect(graph.fitCount).toBe(fitCountBeforeResize);
    expect(graph.viewport).toBe('user-zoom-pan');
  });

  it('does not recreate the graph when the widget only moves', async () => {
    const WidgetAt = ({ x, y }: { x: number; y: number }) => (
      <div style={{ transform: `translate(${x}px, ${y}px)` }}>
        <TopologyMap rawData={payload} />
      </div>
    );
    const view = render(<WidgetAt x={0} y={0} />);
    await waitFor(() => expect(testState.graphs).toHaveLength(1));
    const graph = testState.graphs[0];
    graph.viewport = 'user-zoom-pan';

    view.rerender(<WidgetAt x={240} y={160} />);

    expect(testState.graphs).toHaveLength(1);
    expect(testState.graphs[0]).toBe(graph);
    expect(graph.viewport).toBe('user-zoom-pan');
  });

  it('patches presentation-only data refreshes without losing the viewport', async () => {
    const view = render(<TopologyMap rawData={payload} />);
    await waitFor(() => expect(testState.graphs).toHaveLength(1));
    const graph = testState.graphs[0];
    graph.viewport = 'user-zoom-pan';

    view.rerender(
      <TopologyMap
        rawData={{
          ...payload,
          nodes: [{
            ...payload.nodes[0],
            instance_name: 'Node A refreshed',
            alert_count: 3,
            alert_level: '1',
          }],
        }}
      />,
    );

    expect(testState.graphs).toHaveLength(1);
    expect(testState.graphs[0]).toBe(graph);
    expect(graph.viewport).toBe('user-zoom-pan');
  });

  it('rebuilds and fits only when graph structure changes', async () => {
    const view = render(<TopologyMap rawData={payload} />);
    await waitFor(() => expect(testState.graphs).toHaveLength(1));

    view.rerender(
      <TopologyMap
        rawData={{
          nodes: [
            ...payload.nodes,
            {
              id: 'node-b',
              instance_id: 2,
              instance_name: 'Node B',
              model_name: 'Host',
              alert_count: 0,
            },
          ],
          edges: [{ source: 'node-a', target: 'node-b' }],
        }}
      />,
    );

    await waitFor(() => expect(testState.graphs).toHaveLength(2));
    expect(testState.graphs[1].fitCount).toBe(1);
  });
});
