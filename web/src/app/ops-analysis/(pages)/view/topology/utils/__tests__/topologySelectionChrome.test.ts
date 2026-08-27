import { describe, expect, it } from 'vitest';
import {
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
});
