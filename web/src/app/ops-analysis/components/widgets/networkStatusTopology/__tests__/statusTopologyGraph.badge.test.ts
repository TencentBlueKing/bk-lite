// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';

vi.mock('@antv/x6', () => ({
  Graph: {
    registerConnector: vi.fn(),
    registerNode: vi.fn(),
  },
}));

vi.mock('@/app/cmdb/utils/common', () => ({
  getIconUrl: () => '',
}));

import { isStatusTopologyBadgeTarget } from '../statusTopologyGraph';

describe('isStatusTopologyBadgeTarget', () => {
  it('matches composedPath elements with the badge class', () => {
    const badge = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    badge.classList.add('status-topo-alert-badge');
    const event = new MouseEvent('click');
    Object.defineProperty(event, 'composedPath', {
      value: () => [badge],
    });
    expect(isStatusTopologyBadgeTarget(event)).toBe(true);
  });

  it('ignores events whose path has no badge class', () => {
    const other = document.createElementNS('http://www.w3.org/2000/svg', 'image');
    const event = new MouseEvent('click');
    Object.defineProperty(event, 'composedPath', {
      value: () => [other],
    });
    expect(isStatusTopologyBadgeTarget(event)).toBe(false);
  });
});
