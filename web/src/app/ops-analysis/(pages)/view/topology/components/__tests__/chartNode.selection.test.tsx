// @vitest-environment jsdom

import React from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setTopologyCsvExportHoverEnabled } from '../../utils/topologyCsvExportHover';
import {
  resetInteractionRuntime,
  setInteractionRuntime,
} from '@/app/ops-analysis/context/interactionRuntime';
import type { Node } from '@antv/x6';
import ChartNode from '../chartNode';
import {
  applyTopologyNodeHoverChrome,
  clearTopologyNodeHoverChrome,
  highlightTopologyNode,
  resetTopologyNodeChrome,
  TOPOLOGY_CHART_NODE_CLASS,
  TOPOLOGY_CHART_NODE_HOVER_CLASS,
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
  expect(chrome.classList.contains(TOPOLOGY_CHART_NODE_HOVER_CLASS)).toBe(
    false,
  );
  expect(chrome.getAttribute('data-topology-selected')).toBe('true');
  expect(chrome.getAttribute('data-topology-hover')).toBe('false');
  expect(chrome.style.border).toBe('2px solid var(--color-primary)');
};

const expectUnselectedChrome = (chrome: HTMLElement) => {
  expect(chrome.classList.contains(TOPOLOGY_CHART_NODE_SELECTED_CLASS)).toBe(
    false,
  );
  expect(chrome.classList.contains(TOPOLOGY_CHART_NODE_HOVER_CLASS)).toBe(
    false,
  );
  expect(chrome.getAttribute('data-topology-selected')).toBe('false');
  expect(chrome.getAttribute('data-topology-hover')).toBe('false');
  expect(chrome.style.border).toMatch(/^1px solid /);
  expect(chrome.style.border).not.toContain('var(--color-primary)');
  expect(chrome.style.border).not.toContain('rgb(24, 144, 255)');
  expect(chrome.style.cursor).not.toBe('pointer');
};

const expectViewHoverChrome = (chrome: HTMLElement) => {
  expect(chrome.classList.contains(TOPOLOGY_CHART_NODE_SELECTED_CLASS)).toBe(
    false,
  );
  expect(chrome.classList.contains(TOPOLOGY_CHART_NODE_HOVER_CLASS)).toBe(true);
  expect(chrome.getAttribute('data-topology-selected')).toBe('false');
  expect(chrome.getAttribute('data-topology-hover')).toBe('true');
  expect(chrome.style.border).toBe('1px solid var(--color-border-2)');
  expect(chrome.style.cursor).toBe('pointer');
  expect(chrome.style.outline).toBe('none');
  expect(chrome.style.border).not.toContain('var(--color-primary)');
};

afterEach(cleanup);

describe('ChartNode selection chrome', () => {
  afterEach(() => {
    setTopologyCsvExportHoverEnabled(false);
    resetInteractionRuntime('title-link-test');
    cleanup();
  });

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
    const selectedBorder = chrome.style.border;

    act(() => {
      applyTopologyNodeHoverChrome(node, true, true);
    });
    expectSelectedChrome(chrome);
    expect(chrome.style.border).toBe(selectedBorder);

    act(() => {
      clearTopologyNodeHoverChrome(node, true);
    });
    expectSelectedChrome(chrome);
    expect(chrome.style.border).toBe(selectedBorder);
  });

  it('shows edit-mode hover chrome only while an unselected chart is hovered', () => {
    const node = createChartNode();
    const { container } = render(<ChartNode node={node} />);
    const chrome = getChrome(container);

    expectUnselectedChrome(chrome);

    act(() => {
      applyTopologyNodeHoverChrome(node, false, true);
    });
    expectSelectedChrome(chrome);

    act(() => {
      clearTopologyNodeHoverChrome(node, false);
    });
    expectUnselectedChrome(chrome);
  });

  it('shows view-mode hover chrome without selected blue', () => {
    const node = createChartNode();
    const { container } = render(<ChartNode node={node} />);
    const chrome = getChrome(container);

    expectUnselectedChrome(chrome);

    act(() => {
      applyTopologyNodeHoverChrome(node, false, false);
    });
    expectViewHoverChrome(chrome);

    act(() => {
      clearTopologyNodeHoverChrome(node, false);
    });
    expectUnselectedChrome(chrome);
  });

  it('keeps selected chrome in view mode while hovered', () => {
    const node = createChartNode();
    highlightTopologyNode(node);
    const { container } = render(<ChartNode node={node} />);
    const chrome = getChrome(container);

    expectSelectedChrome(chrome);

    act(() => {
      applyTopologyNodeHoverChrome(node, true, false);
    });
    expectSelectedChrome(chrome);
    expect(chrome.classList.contains(TOPOLOGY_CHART_NODE_HOVER_CLASS)).toBe(
      false,
    );
    expect(chrome.style.border).toBe('2px solid var(--color-primary)');
  });

  it('shows a hover csv icon for supported charts without swallowing wheel events', async () => {
    const onExportCsv = vi.fn();
    const node = createChartNode();
    const data = node.getData();
    node.getData = () => ({ ...data, onExportCsv });
    const { container } = render(<ChartNode node={node} />);
    expect(container.querySelector('[data-csv-export-hover]')).toBeNull();

    act(() => {
      setTopologyCsvExportHoverEnabled(true);
    });
    const button = container.querySelector('[data-csv-export-hover]') as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.className).toContain('opacity-0');
    expect(button.className).toContain('shrink-0');
    expect(button.className).toContain('cursor-pointer');
    expect(button.className).not.toContain('absolute');
    fireEvent.mouseEnter(button);
    await waitFor(() => {
      const tooltip = document.querySelector('[role="tooltip"]');
      expect(tooltip?.textContent).toBe('dashboard.exportCsv');
      expect(button.parentElement?.contains(tooltip)).toBe(false);
    });
    expect(button.parentElement?.textContent).toContain('CPU');
    expect(button.getAttribute('data-export-hidden')).toBe('true');

    const wheel = vi.fn();
    const pointer = vi.fn();
    document.addEventListener('wheel', wheel);
    document.addEventListener('pointerdown', pointer);
    fireEvent.wheel(button);
    fireEvent.pointerDown(button);
    fireEvent.click(button);
    document.removeEventListener('wheel', wheel);
    document.removeEventListener('pointerdown', pointer);
    expect(wheel).toHaveBeenCalled();
    expect(pointer).not.toHaveBeenCalled();
    expect(onExportCsv).toHaveBeenCalledWith('chart-1', 'CPU');

    cleanup();
    const gauge = createChartNode();
    gauge.getData = () => ({
      ...data,
      valueConfig: { chartType: 'gauge' },
    });
    const hidden = render(<ChartNode node={gauge} />);
    expect(hidden.container.querySelector('[data-csv-export-hover]')).toBeNull();

    cleanup();
    const untitled = createChartNode();
    const untitledData = untitled.getData();
    untitled.getData = () => ({ ...untitledData, name: '' });
    const withoutTitle = render(<ChartNode node={untitled} />);
    expect(withoutTitle.container.querySelector('[data-csv-export-hover]')).toBeNull();
    expect(withoutTitle.container.textContent).not.toContain('CPU');
  });

  it('hides the csv icon when radar data is multi-series', () => {
    const node = createChartNode();
    const data = node.getData();
    node.getData = () => ({
      ...data,
      name: '雷达',
      valueConfig: { chartType: 'radar' },
      rawData: {
        hostA: [{ name: 'CPU', value: 70 }],
        hostB: [{ name: 'CPU', value: 60 }],
      },
    });
    const { container } = render(<ChartNode node={node} />);
    act(() => {
      setTopologyCsvExportHoverEnabled(true);
    });
    expect(container.querySelector('[data-csv-export-hover]')).toBeNull();
  });
});

const titleInteraction = {
  kind: 'title' as const,
  name: '查看详情',
  url: '/ops',
  openMode: 'sameTab' as const,
};

const chartWithTitleLink = (
  overrides: Record<string, unknown> = {},
) => {
  const node = createChartNode();
  const data = node.getData() as {
    valueConfig: Record<string, unknown>;
    name?: string;
  };
  node.getData = (() => ({
    ...data,
    ...overrides,
    valueConfig: {
      ...data.valueConfig,
      chartThemeMode: 'screen-dark',
      interaction: titleInteraction,
      ...(overrides.valueConfig as Record<string, unknown> | undefined),
    },
  })) as Node['getData'];
  return node;
};

describe('ChartNode title link', () => {
  afterEach(() => {
    setTopologyCsvExportHoverEnabled(false);
    resetInteractionRuntime('title-link-test');
    cleanup();
  });

  it('places the chevron after the csv download and colors it with the title', () => {
    const node = chartWithTitleLink();
    const { container } = render(<ChartNode node={node} />);
    act(() => {
      setTopologyCsvExportHoverEnabled(true);
    });

    const link = container.querySelector('button[aria-label="查看详情"]') as HTMLButtonElement;
    const title = container.querySelector('.truncate') as HTMLElement;
    const csv = container.querySelector('[data-csv-export-hover]') as HTMLElement;

    expect(link.querySelector('.anticon-export')).toBeTruthy();
    expect(link.querySelector('.anticon-share-alt')).toBeNull();
    expect(link.className).toContain('w-0');
    expect(link.className).toContain('group-hover:w-5');
    expect(link.className).not.toContain('absolute');
    expect(link.className).not.toContain('text-(--color-text-3)');
    expect(title.textContent).toBe('CPU');
    expect(link.style.color).toBe('rgb(232, 238, 247)');
    expect(link.style.color).toBe(title.style.color);
    expect(link.getAttribute('data-export-hidden')).toBe('true');
    expect(link.className).toContain('no-drag');
    const row = title.parentElement?.parentElement as HTMLElement;
    expect(csv.compareDocumentPosition(link) & globalThis.Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(row.lastElementChild === link || row.lastElementChild?.contains(link)).toBe(true);
    expect(title.closest('button')).toBeNull();
  });

  it('keeps an untitled chevron at the top right and still follows the title color', () => {
    const node = chartWithTitleLink({ name: '' });
    const { container } = render(<ChartNode node={node} />);
    const link = container.querySelector('button[aria-label="查看详情"]') as HTMLButtonElement;

    expect(link.querySelector('.anticon-export')).toBeTruthy();
    expect(link.className).not.toContain('w-0');
    expect(link.className).toContain('absolute');
    expect(link.className).toContain('right-2');
    expect(link.className).toContain('top-2');
    expect(link.style.color).toBe('rgb(232, 238, 247)');
    expect(link.className).not.toContain('text-(--color-text-3)');
    expect(container.querySelector('[data-csv-export-hover]')).toBeNull();
  });

  it('hides the chevron on the share surface', () => {
    setInteractionRuntime({
      surface: 'share',
      definitions: [],
      values: {},
    }, 'title-link-test');
    const node = chartWithTitleLink();
    const { container } = render(<ChartNode node={node} />);

    expect(container.textContent).toContain('CPU');
    expect(container.querySelector('button[aria-label="查看详情"]')).toBeNull();
  });
});
