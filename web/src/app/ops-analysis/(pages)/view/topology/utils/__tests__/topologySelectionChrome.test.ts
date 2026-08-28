import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  applyTopologyNodeHoverChrome,
  clearTopologyNodeHoverChrome,
  getTopologyNodeResetStroke,
  highlightTopologyNode,
  isTopologyNodeSelectionChrome,
  resetTopologyNodeChrome,
} from '../topologySelectionChrome';

interface AttrNode {
  data: { type?: string; styleConfig?: { borderColor?: string } };
  attrs: { body?: { stroke?: string; strokeWidth?: number } };
  getData: () => AttrNode['data'];
  getAttrByPath: (path: string) => unknown;
  setAttrByPath: (path: string, value: unknown) => void;
}

const createNode = (
  data: AttrNode['data'] = {},
  attrs: AttrNode['attrs'] = {},
): AttrNode => {
  const node: AttrNode = {
    data,
    attrs,
    getData: () => node.data,
    getAttrByPath: (path: string) => {
      if (path === 'body/stroke') return node.attrs.body?.stroke;
      if (path === 'body/strokeWidth') return node.attrs.body?.strokeWidth;
      return undefined;
    },
    setAttrByPath: (path: string, value: unknown) => {
      node.attrs.body = node.attrs.body || {};
      if (path === 'body/stroke') {
        node.attrs.body.stroke = value as string;
      }
      if (path === 'body/strokeWidth') {
        node.attrs.body.strokeWidth = value as number;
      }
    },
  };
  return node;
};

describe('topologySelectionChrome', () => {
  it('applies the same selected stroke to chart and non-chart nodes', () => {
    const chart = createNode({ type: 'chart' });
    const text = createNode({ type: 'text' });
    const icon = createNode({ type: 'icon' });
    const single = createNode({ type: 'single-value' });

    for (const node of [chart, text, icon, single]) {
      highlightTopologyNode(node);
      expect(node.getAttrByPath('body/stroke')).toBe('#1890FF');
      expect(node.getAttrByPath('body/strokeWidth')).toBe(2);
      expect(isTopologyNodeSelectionChrome(node)).toBe(true);
    }
  });

  it('does not treat an unselected chart as highlighted', () => {
    const chart = createNode({ type: 'chart' });
    expect(isTopologyNodeSelectionChrome(chart)).toBe(false);
    resetTopologyNodeChrome(chart);
    expect(isTopologyNodeSelectionChrome(chart)).toBe(false);
    expect(chart.getAttrByPath('body/stroke')).not.toBe('#1890FF');
  });

  it('restores type-specific unselected strokes', () => {
    expect(getTopologyNodeResetStroke({ type: 'text' })).toBe('transparent');
    expect(
      getTopologyNodeResetStroke({
        type: 'single-value',
        styleConfig: { borderColor: 'transparent' },
      }),
    ).toBe('transparent');
    expect(
      getTopologyNodeResetStroke({
        type: 'icon',
        styleConfig: { borderColor: '#e0ddddff' },
      }),
    ).toBe('#e0ddddff');
  });

  it.each(['icon', 'single-value', 'chart'] as const)(
    'keeps selected chrome on %s nodes while hovered and after mouse leave',
    (type) => {
      const node = createNode({ type });
      highlightTopologyNode(node);

      applyTopologyNodeHoverChrome(node, true);
      expect(isTopologyNodeSelectionChrome(node)).toBe(true);
      expect(node.getAttrByPath('body/stroke')).toBe('#1890FF');
      expect(node.getAttrByPath('body/strokeWidth')).toBe(2);

      clearTopologyNodeHoverChrome(node, true);
      expect(isTopologyNodeSelectionChrome(node)).toBe(true);
      expect(node.getAttrByPath('body/stroke')).toBe('#1890FF');
      expect(node.getAttrByPath('body/strokeWidth')).toBe(2);
    },
  );

  it.each(['icon', 'single-value', 'chart'] as const)(
    'applies hover chrome only to unselected %s nodes and resets on leave',
    (type) => {
      const node = createNode({
        type,
        styleConfig: { borderColor: type === 'icon' ? '#e0ddddff' : 'transparent' },
      });

      expect(isTopologyNodeSelectionChrome(node)).toBe(false);

      applyTopologyNodeHoverChrome(node, false);
      expect(isTopologyNodeSelectionChrome(node)).toBe(true);

      clearTopologyNodeHoverChrome(node, false);
      expect(isTopologyNodeSelectionChrome(node)).toBe(false);
      if (type === 'icon') {
        expect(node.getAttrByPath('body/stroke')).toBe('#e0ddddff');
      } else {
        expect(node.getAttrByPath('body/stroke')).not.toBe('#1890FF');
      }
    },
  );

  it('wires hover chrome to live graph selection instead of a stale selectedCells snapshot', () => {
    const source = readFileSync(
      path.join(__dirname, '../../hooks/useGraphInitializer.ts'),
      'utf8',
    );
    expect(source).toContain(
      'applyTopologyNodeHoverChrome(node, graph.isSelected(node))',
    );
    expect(source).toContain(
      'clearTopologyNodeHoverChrome(node, graph.isSelected(node))',
    );
    expect(source).not.toContain('selectedCells.includes(node.id)');
  });

  it('keeps selected outline CSS above icon/chart hover chrome', () => {
    const source = readFileSync(
      path.join(__dirname, '../../index.module.scss'),
      'utf8',
    );
    expect(source).toContain(
      ".x6-node[data-shape='icon-node']:hover:not(.x6-node-selected):not(.selected)",
    );
    expect(source).toContain(
      ".x6-node-selected[data-shape='icon-node']:hover rect[selector='body']",
    );
    expect(source).toContain(
      ".x6-node-selected[data-shape='single-value-node']:hover rect[selector='body']",
    );
    expect(source).toContain(
      '.ops-topology-chart-node.ops-topology-chart-node--selected:hover',
    );
  });
});
