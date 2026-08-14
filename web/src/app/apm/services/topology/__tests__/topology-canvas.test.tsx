import React from 'react';
import { cleanup, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import type { ApmTopologyEdge, ApmTopologyNode } from '@/app/apm/types';
import { TopologyCanvas } from '../page';

const node = (id: string): ApmTopologyNode => ({
  id,
  service_namespace: 'apm-demo-shop',
  service_name: id,
  environment: 'local',
  health: 'healthy',
  sampled_spans: 100,
  error_spans: 0,
});

const edge = (source: string, target: string): ApmTopologyEdge => ({
  source,
  target,
  health: 'healthy',
  sampled_calls: 10,
  error_calls: 0,
  average_duration_ms: 12,
});

const nodes = [node('catalog'), node('inventory'), node('storefront')];
const edges = [edge('catalog', 'inventory'), edge('storefront', 'catalog')];

const edgePairs = (container: HTMLElement) => Array.from(
  container.querySelectorAll<SVGGElement>('g[data-source][data-target]'),
).map((item) => `${item.dataset.source}>${item.dataset.target}`).sort();

afterEach(cleanup);

describe('APM 服务拓扑画布', () => {
  it('切换布局只改变坐标，不改变依赖方向或箭头端点', async () => {
    const result = renderWithApmIntl(
      <TopologyCanvas edges={edges} keyword="" layout="layered" nodes={nodes} zoom={1} />,
    );

    await waitFor(() => {
      expect(edgePairs(result.container)).toEqual(['catalog>inventory', 'storefront>catalog']);
    });
    result.container.querySelectorAll<SVGPathElement>('g[data-source] > path').forEach((path) => {
      expect(path.getAttribute('marker-end')).toBe('url(#apm-arrow-healthy)');
      expect(path.getAttribute('marker-start')).toBeNull();
    });

    result.rerender(
      <TopologyCanvas edges={edges} keyword="" layout="radial" nodes={nodes} zoom={1} />,
    );

    await waitFor(() => {
      expect(edgePairs(result.container)).toEqual(['catalog>inventory', 'storefront>catalog']);
    });
    result.container.querySelectorAll<SVGPathElement>('g[data-source] > path').forEach((path) => {
      expect(path.getAttribute('marker-end')).toBe('url(#apm-arrow-healthy)');
      expect(path.getAttribute('marker-start')).toBeNull();
    });
  });
});
