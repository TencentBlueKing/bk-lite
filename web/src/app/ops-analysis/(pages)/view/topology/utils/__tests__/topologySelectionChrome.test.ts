import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  applyTopologyNodeHoverChrome,
  clearTopologyNodeHoverChrome,
  getTopologyNodeChromeKind,
  getTopologyNodeResetStroke,
  highlightTopologyNode,
  isTopologyNodeSelectionChrome,
  isTopologyNodeViewHoverChrome,
  resetTopologyNodeChrome,
  TOPOLOGY_SELECTED_STROKE,
  TOPOLOGY_VIEW_HOVER_STROKE,
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

const expectViewHoverChrome = (node: AttrNode) => {
  expect(isTopologyNodeViewHoverChrome(node)).toBe(true);
  expect(isTopologyNodeSelectionChrome(node)).toBe(false);
  expect(getTopologyNodeChromeKind(node)).toBe('view-hover');
  expect(node.getAttrByPath('body/stroke')).toBe(TOPOLOGY_VIEW_HOVER_STROKE);
  expect(node.getAttrByPath('body/strokeWidth')).toBe(1);
  expect(node.getAttrByPath('body/stroke')).not.toBe(TOPOLOGY_SELECTED_STROKE);
  expect(node.getAttrByPath('body/stroke')).not.toBe('#1890FF');
};

describe('topologySelectionChrome', () => {
  it('applies the same selected stroke to chart and non-chart nodes', () => {
    const chart = createNode({ type: 'chart' });
    const text = createNode({ type: 'text' });
    const icon = createNode({ type: 'icon' });
    const single = createNode({ type: 'single-value' });

    for (const node of [chart, text, icon, single]) {
      highlightTopologyNode(node);
      expect(node.getAttrByPath('body/stroke')).toBe('var(--color-primary)');
      expect(node.getAttrByPath('body/strokeWidth')).toBe(2);
      expect(isTopologyNodeSelectionChrome(node)).toBe(true);
      expect(getTopologyNodeChromeKind(node)).toBe('selected');
    }
  });

  it('does not treat an unselected chart as highlighted', () => {
    const chart = createNode({ type: 'chart' });
    expect(isTopologyNodeSelectionChrome(chart)).toBe(false);
    resetTopologyNodeChrome(chart);
    expect(isTopologyNodeSelectionChrome(chart)).toBe(false);
    expect(getTopologyNodeChromeKind(chart)).toBe('rest');
    expect(chart.getAttrByPath('body/stroke')).not.toBe('var(--color-primary)');
    expect(chart.getAttrByPath('body/stroke')).not.toBe('#1890FF');
  });

  it('treats the legacy primary hex as selected chrome', () => {
    const node = createNode({ type: 'icon' });
    node.setAttrByPath('body/stroke', '#1890FF');
    expect(isTopologyNodeSelectionChrome(node)).toBe(true);
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
      const selectedStroke = node.getAttrByPath('body/stroke');
      const selectedWidth = node.getAttrByPath('body/strokeWidth');
      const writes: string[] = [];
      const originalSet = node.setAttrByPath;
      node.setAttrByPath = (path, value) => {
        writes.push(path);
        originalSet(path, value);
      };

      applyTopologyNodeHoverChrome(node, true, true);
      expect(writes).toEqual([]);
      expect(isTopologyNodeSelectionChrome(node)).toBe(true);
      expect(node.getAttrByPath('body/stroke')).toBe(selectedStroke);
      expect(node.getAttrByPath('body/strokeWidth')).toBe(selectedWidth);
      expect(node.getAttrByPath('body/stroke')).toBe(TOPOLOGY_SELECTED_STROKE);

      clearTopologyNodeHoverChrome(node, true);
      expect(isTopologyNodeSelectionChrome(node)).toBe(true);
      expect(node.getAttrByPath('body/stroke')).toBe(TOPOLOGY_SELECTED_STROKE);
      expect(node.getAttrByPath('body/strokeWidth')).toBe(2);
    },
  );

  it.each(['icon', 'single-value', 'chart'] as const)(
    'applies edit-mode hover chrome only to unselected %s nodes and resets on leave',
    (type) => {
      const node = createNode({
        type,
        styleConfig: { borderColor: type === 'icon' ? '#e0ddddff' : 'transparent' },
      });

      expect(isTopologyNodeSelectionChrome(node)).toBe(false);

      applyTopologyNodeHoverChrome(node, false, true);
      expect(isTopologyNodeSelectionChrome(node)).toBe(true);
      expect(isTopologyNodeViewHoverChrome(node)).toBe(false);
      expect(getTopologyNodeChromeKind(node)).toBe('selected');

      clearTopologyNodeHoverChrome(node, false);
      expect(isTopologyNodeSelectionChrome(node)).toBe(false);
      expect(getTopologyNodeChromeKind(node)).toBe('rest');
      if (type === 'icon') {
        expect(node.getAttrByPath('body/stroke')).toBe('#e0ddddff');
      } else {
        expect(node.getAttrByPath('body/stroke')).not.toBe(
          TOPOLOGY_SELECTED_STROKE,
        );
        expect(node.getAttrByPath('body/stroke')).not.toBe('#1890FF');
      }
    },
  );

  it.each(['icon', 'single-value', 'chart'] as const)(
    'applies view-mode hover chrome to unselected %s nodes without selected blue',
    (type) => {
      const restBorder = type === 'icon' ? '#e0ddddff' : 'transparent';
      const node = createNode({
        type,
        styleConfig: { borderColor: restBorder },
      });

      applyTopologyNodeHoverChrome(node, false, false);
      expectViewHoverChrome(node);

      clearTopologyNodeHoverChrome(node, false);
      expect(isTopologyNodeViewHoverChrome(node)).toBe(false);
      expect(isTopologyNodeSelectionChrome(node)).toBe(false);
      expect(getTopologyNodeChromeKind(node)).toBe('rest');
      if (type === 'icon') {
        expect(node.getAttrByPath('body/stroke')).toBe('#e0ddddff');
      } else {
        expect(node.getAttrByPath('body/stroke')).toBe('transparent');
      }
      expect(node.getAttrByPath('body/strokeWidth')).toBe(1);
    },
  );

  it.each(['icon', 'single-value', 'chart'] as const)(
    'keeps view-mode selected chrome on %s nodes while hovered and after leave',
    (type) => {
      const node = createNode({ type });
      highlightTopologyNode(node);
      const writes: string[] = [];
      const originalSet = node.setAttrByPath;
      node.setAttrByPath = (path, value) => {
        writes.push(path);
        originalSet(path, value);
      };

      applyTopologyNodeHoverChrome(node, true, false);
      expect(writes).toEqual([]);
      expect(isTopologyNodeSelectionChrome(node)).toBe(true);
      expect(isTopologyNodeViewHoverChrome(node)).toBe(false);
      expect(node.getAttrByPath('body/stroke')).toBe(TOPOLOGY_SELECTED_STROKE);
      expect(node.getAttrByPath('body/strokeWidth')).toBe(2);

      clearTopologyNodeHoverChrome(node, true);
      expect(isTopologyNodeSelectionChrome(node)).toBe(true);
      expect(node.getAttrByPath('body/stroke')).toBe(TOPOLOGY_SELECTED_STROKE);
    },
  );

  it('wires hover chrome to live graph selection and edit-mode port visibility', () => {
    const source = readFileSync(
      path.join(__dirname, '../../hooks/useGraphInitializer.ts'),
      'utf8',
    );
    expect(source).toContain('graph.isSelected(node)');
    expect(source).toContain('isEditModeRef.current');
    expect(source).toContain('applyTopologyNodeHoverChrome(');
    expect(source).toContain(
      'clearTopologyNodeHoverChrome(node, graph.isSelected(node))',
    );
    expect(source).not.toContain('selectedCells.includes(node.id)');
    expect(source).toMatch(
      /if \(isEditModeRef\.current\) \{\s*showPorts\(graph, node\);\s*\}/,
    );
    expect(source).not.toMatch(
      /hideAllEdgeTools\(graph\);\s*showPorts\(graph, node\);/,
    );
  });

  it('keeps selected outline CSS above icon/chart hover chrome', () => {
    const source = readFileSync(
      path.join(__dirname, '../../index.module.scss'),
      'utf8',
    );
    expect(source).toContain(
      ".x6-node[data-shape='icon-node']:hover:not(.x6-node-selected):not(.selected)",
    );
    const iconSelectedBlock = source.slice(
      source.indexOf(
        ".x6-node-selected[data-shape='icon-node'] rect[selector='body']",
      ),
      source.indexOf(
        ".x6-node-selected[data-shape='single-value-node'] rect[selector='body']",
      ),
    );
    const chartSelectedBlock = source.slice(
      source.indexOf(
        '.ops-topology-chart-node.ops-topology-chart-node--selected',
      ),
      source.indexOf(".x6-node[data-shape='icon-node'] text[selector='label']"),
    );
    expect(iconSelectedBlock).toContain(
      ".x6-node-selected[data-shape='icon-node']:hover rect[selector='body']",
    );
    expect(iconSelectedBlock).toContain('stroke: var(--color-primary)');
    expect(iconSelectedBlock).not.toContain('#2d7df0');
    expect(iconSelectedBlock).not.toContain('#8dbcf2');
    expect(chartSelectedBlock).toContain(
      '.ops-topology-chart-node.ops-topology-chart-node--selected:hover',
    );
    expect(chartSelectedBlock).toContain(
      'border-color: var(--color-primary)',
    );
    expect(source).toContain(
      ".x6-node-selected[data-shape='single-value-node']:hover rect[selector='body']",
    );
  });

  it('scopes edit-mode icon hover and view-mode hover chrome in CSS', () => {
    const source = readFileSync(
      path.join(__dirname, '../../index.module.scss'),
      'utf8',
    );
    const pageSource = readFileSync(
      path.join(__dirname, '../../index.tsx'),
      'utf8',
    );
    expect(pageSource).toContain(
      "data-topology-mode={state.isEditMode ? 'edit' : 'view'}",
    );

    const editBlock = source.slice(
      source.indexOf(".topologyContainer[data-topology-mode='edit']"),
      source.indexOf(".topologyContainer[data-topology-mode='view']"),
    );
    expect(editBlock).toContain('#8dbcf2');
    expect(editBlock).not.toContain('var(--color-border-2)');

    const viewStart = source.indexOf(
      ".topologyContainer[data-topology-mode='view']",
    );
    const viewEnd = source.indexOf('.minimapContainer');
    const viewBlock = source.slice(viewStart, viewEnd);
    expect(viewBlock).toContain('cursor: pointer');
    expect(viewBlock).toContain('stroke: var(--color-border-2)');
    expect(viewBlock).toContain('stroke-width: 1px');
    expect(viewBlock).toContain('outline: none');
    expect(viewBlock).not.toContain('var(--color-primary)');
    expect(viewBlock).not.toContain('#8dbcf2');
    expect(viewBlock).toContain(
      ".x6-node[data-shape='icon-node']:hover:not(.x6-node-selected):not(.selected) rect[selector='body']",
    );
    expect(viewBlock).toContain(
      ".x6-node[data-shape='single-value-node']:hover:not(.x6-node-selected):not(.selected) rect[selector='body']",
    );
    expect(viewBlock).toContain(
      ".x6-node[data-shape='chart-node']:hover:not(.x6-node-selected):not(.selected) rect[selector='body']",
    );
    expect(viewBlock).toContain(
      '.ops-topology-chart-node:hover:not(.ops-topology-chart-node--selected)',
    );
  });
});
