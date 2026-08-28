// @vitest-environment jsdom

import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Node } from '@antv/x6';
import ChartNode from '../chartNode';
import {
  applyTopologyNodeHoverChrome,
  clearTopologyNodeHoverChrome,
  highlightTopologyNode,
  resetTopologyNodeChrome,
  TOPOLOGY_CHART_NODE_CLASS,
  TOPOLOGY_CHART_NODE_SELECTED_CLASS,
} from '../../utils/topologySelectionChrome';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/ops-analysis/components/widgetRenderer', () => ({
  default: () => <div data-testid="widget-renderer" />,
}));

const createChartNode = () => {
  const handlers: Record<string, Array<() => void>> = {};
  const attrs: { body?: { stroke?: string; strokeWidth?: number } } = {};
  const node = {
    id: 'chart-1',
    getData: () => ({
      type: 'chart',
      name: 'CPU',
      valueConfig: { chartType: 'line' },
      styleConfig: { width: 400, height: 220 },
      isLoading: true,
      rawData: null,
      hasError: false,
    }),
    getAttrByPath: (path: string) => {
      if (path === 'body/stroke') return attrs.body?.stroke;
      if (path === 'body/strokeWidth') return attrs.body?.strokeWidth;
      return undefined;
    },
    setAttrByPath: (path: string, value: unknown) => {
      attrs.body = attrs.body || {};
      if (path === 'body/stroke') attrs.body.stroke = value as string;
      if (path === 'body/strokeWidth') attrs.body.strokeWidth = value as number;
      (handlers['change:attrs'] || []).forEach((fn) => fn());
    },
    on: (event: string, fn: () => void) => {
      handlers[event] = handlers[event] || [];
      handlers[event].push(fn);
    },
    off: (event: string, fn: () => void) => {
      handlers[event] = (handlers[event] || []).filter((h) => h !== fn);
    },
  };
  return node as unknown as Node;
};

const getChrome = (container: HTMLElement) =>
  container.querySelector(`.${TOPOLOGY_CHART_NODE_CLASS}`) as HTMLElement;

const expectSelectedChrome = (chrome: HTMLElement) => {
  expect(chrome.classList.contains(TOPOLOGY_CHART_NODE_SELECTED_CLASS)).toBe(
    true,
  );
  expect(chrome.getAttribute('data-topology-selected')).toBe('true');
  expect(chrome.style.border).toBe('2px solid rgb(24, 144, 255)');
};

const expectUnselectedChrome = (chrome: HTMLElement) => {
  expect(chrome.classList.contains(TOPOLOGY_CHART_NODE_SELECTED_CLASS)).toBe(
    false,
  );
  expect(chrome.getAttribute('data-topology-selected')).toBe('false');
  expect(chrome.style.border).toMatch(/^1px solid /);
  expect(chrome.style.border).not.toContain('rgb(24, 144, 255)');
};

afterEach(cleanup);

describe('ChartNode selection chrome', () => {
  it('shows the selected border after topology highlight attrs are applied', () => {
    const node = createChartNode();
    const { container } = render(<ChartNode node={node} />);
    const chrome = getChrome(container);

    expectUnselectedChrome(chrome);

    act(() => {
      highlightTopologyNode(node);
    });

    expectSelectedChrome(chrome);
  });

  it('shows selected chrome when highlight attrs are already present', () => {
    const node = createChartNode();
    highlightTopologyNode(node);
    const { container } = render(<ChartNode node={node} />);
    const chrome = getChrome(container);

    expectSelectedChrome(chrome);
  });

  it('does not keep selected chrome on an unselected chart', () => {
    const node = createChartNode();
    const { container } = render(<ChartNode node={node} />);
    const chrome = getChrome(container);

    act(() => {
      highlightTopologyNode(node);
    });
    act(() => {
      resetTopologyNodeChrome(node);
    });

    expectUnselectedChrome(chrome);
  });

  it('keeps selected chrome while hovered and after mouse leave', () => {
    const node = createChartNode();
    highlightTopologyNode(node);
    const { container } = render(<ChartNode node={node} />);
    const chrome = getChrome(container);

    expectSelectedChrome(chrome);

    act(() => {
      applyTopologyNodeHoverChrome(node, true);
    });
    expectSelectedChrome(chrome);

    act(() => {
      clearTopologyNodeHoverChrome(node, true);
    });
    expectSelectedChrome(chrome);
  });

  it('shows hover chrome only while an unselected chart is hovered', () => {
    const node = createChartNode();
    const { container } = render(<ChartNode node={node} />);
    const chrome = getChrome(container);

    expectUnselectedChrome(chrome);

    act(() => {
      applyTopologyNodeHoverChrome(node, false);
    });
    expectSelectedChrome(chrome);

    act(() => {
      clearTopologyNodeHoverChrome(node, false);
    });
    expectUnselectedChrome(chrome);
  });
});
