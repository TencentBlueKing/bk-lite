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

import {
  buildStatusTopologyX6GraphData,
  buildPortLabelHitBox,
  getStatusTopologyPortHoverEnd,
  isStatusTopologyBadgeTarget,
  resolveStatusTopologyLinkStroke,
  STATUS_TOPOLOGY_LINK_CROSS_TEXT,
  STATUS_TOPOLOGY_PALETTE_LIGHT,
  STATUS_TOPOLOGY_PORT_LABEL_CLASS,
  STATUS_TOPOLOGY_VISUAL,
  wrapTopologyLabel,
} from '../statusTopologyGraph';

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

describe('getStatusTopologyPortHoverEnd', () => {
  it('reads source/target from the port label class', () => {
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.classList.add(STATUS_TOPOLOGY_PORT_LABEL_CLASS);
    label.setAttribute('data-port-end', 'source');
    const event = new MouseEvent('mouseenter');
    Object.defineProperty(event, 'target', { value: label });
    expect(getStatusTopologyPortHoverEnd(event)).toBe('source');
  });

  it('reads the port end from a wrapped tspan ancestor', () => {
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('data-port-end', 'target');
    const tspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
    label.appendChild(tspan);
    const event = new MouseEvent('mouseenter');
    Object.defineProperty(event, 'target', { value: tspan });
    Object.defineProperty(event, 'composedPath', { value: () => [tspan, label] });
    expect(getStatusTopologyPortHoverEnd(event)).toBe('target');
  });

  it('ignores the disconnected cross and the line itself', () => {
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    const event = new MouseEvent('mouseenter');
    Object.defineProperty(event, 'target', { value: line });
    Object.defineProperty(event, 'composedPath', { value: () => [line] });
    expect(getStatusTopologyPortHoverEnd(event)).toBeNull();
  });
});

describe('wrapTopologyLabel', () => {
  it('keeps short names on one line', () => {
    expect(wrapTopologyLabel('switch', 12)).toBe('switch');
  });

  it('wraps device names at a hyphen inside the first line', () => {
    expect(wrapTopologyLabel('10.10.69.246-switch', 12)).toBe('10.10.69.246-\nswitch');
  });

  it('wraps interface names before the first digit group', () => {
    expect(wrapTopologyLabel('GigabitEthernet0/0/5', 12)).toBe('GigabitEthernet\n0/0/5');
  });

  it('does not truncate with an ellipsis', () => {
    expect(wrapTopologyLabel('10.10.69.246-switch', 12)).not.toContain('…');
    expect(wrapTopologyLabel('GigabitEthernet0/0/5', 12)).not.toContain('…');
  });
});

describe('buildStatusTopologyX6GraphData link runtime', () => {
  const nodes = [{
    id: 'a',
    modelId: 'switch',
    name: 'A',
    x: 0,
    y: 0,
  }];

  it('puts traffic with the port name, offsets source and target, and a midpoint cross on down links', () => {
    const { edges } = buildStatusTopologyX6GraphData({
      nodes,
      links: [{
        id: 'l1',
        source: 'a',
        target: 'b',
        sourcePort: 'Gi0/1',
        targetPort: 'Gi0/2',
        disconnected: true,
        sourceTrafficLines: ['↓ 8 B/s'],
        targetTrafficLines: ['↑ 3 B/s'],
      }],
    });
    const labels = edges[0].labels as Array<{
      position?: { distance?: number; offset?: number };
      attrs?: Record<string, {
        text?: string;
        class?: string;
        pointerEvents?: string;
        'data-port-end'?: string;
        fill?: string;
        width?: number;
        height?: number;
        y?: number;
        ref?: string | null;
      }>;
    }>;
    const source = labels.find((label) => label.attrs?.txt?.['data-port-end'] === 'source');
    const target = labels.find((label) => label.attrs?.txt?.['data-port-end'] === 'target');
    const cross = labels.find((label) => label.attrs?.cross?.text === STATUS_TOPOLOGY_LINK_CROSS_TEXT);
    expect(source?.attrs?.txt?.text).toBe('Gi0/1');
    expect(source?.attrs?.traffic0?.text).toBe('↓ 8 B/s');
    expect(target?.attrs?.txt?.text).toBe('Gi0/2');
    expect(target?.attrs?.traffic0?.text).toBe('↑ 3 B/s');
    expect(source?.position?.offset).toBeGreaterThan(0);
    expect(target?.position?.offset).toBeLessThan(0);
    expect(source?.attrs?.text?.pointerEvents).toBe('all');
    expect(source?.attrs?.hit?.pointerEvents).toBe('all');
    expect(source?.attrs?.txt?.pointerEvents).toBe('all');
    expect(source?.attrs?.rect?.ref).toBeNull();
    expect(source?.attrs?.rect?.fill).toBe('none');
    expect(source?.attrs?.hit?.fill).toBe('none');
    expect(Number(source?.attrs?.hit?.width)).toBeGreaterThanOrEqual(
      STATUS_TOPOLOGY_VISUAL.portHitMinWidth,
    );
    expect(Number(source?.attrs?.hit?.height)).toBeGreaterThan(
      STATUS_TOPOLOGY_VISUAL.portLabelLineHeight,
    );
    expect(cross).toBeTruthy();
  });

  it('wraps long node and port names instead of truncating them', () => {
    const { nodes: graphNodes, edges } = buildStatusTopologyX6GraphData({
      nodes: [{
        id: 'a',
        modelId: 'switch',
        name: '10.10.69.246-switch',
        x: 0,
        y: 0,
      }],
      links: [{
        id: 'l1',
        source: 'a',
        target: 'b',
        sourcePort: 'GigabitEthernet0/0/5',
        targetPort: 'GigabitEthernet1',
      }],
    });
    expect(graphNodes[0].attrs.lbl.text).toBe('10.10.69.246-\nswitch');
    expect(graphNodes[0].attrs.lbl.text).not.toContain('…');
    const labels = edges[0].labels as Array<{ attrs?: Record<string, { text?: string; 'data-port-end'?: string }> }>;
    const source = labels.find((label) => label.attrs?.txt?.['data-port-end'] === 'source');
    expect(source?.attrs?.txt?.text).toBe('GigabitEthernet\n0/0/5');
    expect(source?.attrs?.txt?.text).not.toContain('…');
  });

  it('stacks wrapped port names and traffic as consecutive lines', () => {
    const { edges } = buildStatusTopologyX6GraphData({
      nodes,
      links: [{
        id: 'l1',
        source: 'a',
        target: 'b',
        sourcePort: 'GigabitEthernet0/0/4',
        sourceTrafficLines: ['↓ 412.78 B/s', '↑ 10 B/s'],
      }],
    });
    const labels = edges[0].labels as Array<{
      attrs?: Record<string, { text?: string; 'data-port-end'?: string; y?: number; fill?: string }>;
    }>;
    const source = labels.find((label) => label.attrs?.txt?.['data-port-end'] === 'source');
    expect(source?.attrs?.txt?.text).toBe('GigabitEthernet\n0/0/4');
    expect(source?.attrs?.traffic0?.text).toBe('↓ 412.78 B/s');
    expect(source?.attrs?.traffic1?.text).toBe('↑ 10 B/s');
    expect(Number(source?.attrs?.traffic0?.y)).toBeGreaterThan(
      STATUS_TOPOLOGY_VISUAL.portLabelLineHeight,
    );
    expect(Number(source?.attrs?.traffic1?.y)).toBeGreaterThan(
      Number(source?.attrs?.traffic0?.y),
    );
  });

  it('colors inbound and outbound traffic from per-line fills', () => {
    const { edges } = buildStatusTopologyX6GraphData({
      nodes,
      links: [{
        id: 'l1',
        source: 'a',
        target: 'b',
        sourcePort: 'Gi0/1',
        sourceTrafficLines: [
          { text: '↓ 8 B/s', fill: '#dc2626' },
          { text: '↑ 3 B/s', fill: '#d97706' },
        ],
      }],
    });
    const labels = edges[0].labels as Array<{
      attrs?: Record<string, { text?: string; fill?: string; 'data-port-end'?: string }>;
    }>;
    const source = labels.find((label) => label.attrs?.txt?.['data-port-end'] === 'source');
    expect(source?.attrs?.traffic0?.fill).toBe('#dc2626');
    expect(source?.attrs?.traffic1?.fill).toBe('#d97706');
  });

  it('builds a hit box larger than the painted text', () => {
    const hit = buildPortLabelHitBox(2, 2);
    expect(hit.width).toBe(STATUS_TOPOLOGY_VISUAL.portHitMinWidth);
    expect(hit.height).toBeGreaterThan(STATUS_TOPOLOGY_VISUAL.portLabelLineHeight * 4);
    expect(hit.x).toBeLessThan(0);
    expect(hit.y).toBeLessThan(0);
  });

  it('omits the cross when the link is not disconnected', () => {
    const { edges } = buildStatusTopologyX6GraphData({
      nodes,
      links: [{
        id: 'l1',
        source: 'a',
        target: 'b',
        sourcePort: 'Gi0/1',
        disconnected: false,
      }],
    });
    const labels = edges[0].labels as Array<{ attrs?: Record<string, { text?: string }> }>;
    expect(labels.some((label) => label.attrs?.cross?.text === STATUS_TOPOLOGY_LINK_CROSS_TEXT)).toBe(false);
  });

  it('paints up green, down red, and unknown with the structure gray', () => {
    const { edges } = buildStatusTopologyX6GraphData({
      nodes,
      links: [
        { id: 'up', source: 'a', target: 'b', connectStatus: 'up' },
        { id: 'down', source: 'a', target: 'b', connectStatus: 'down', disconnected: true },
        { id: 'unknown', source: 'a', target: 'b', connectStatus: 'unknown' },
      ],
    });
    expect(edges[0].attrs.line.stroke).toBe(STATUS_TOPOLOGY_VISUAL.status.normal);
    expect(edges[1].attrs.line.stroke).toBe(STATUS_TOPOLOGY_VISUAL.status.critical);
    expect(edges[2].attrs.line.stroke).toBe(STATUS_TOPOLOGY_PALETTE_LIGHT.edgeStroke);
  });

  it('keeps the fault-path stroke red even when the link is up', () => {
    expect(
      resolveStatusTopologyLinkStroke(
        { connectStatus: 'up' },
        STATUS_TOPOLOGY_PALETTE_LIGHT,
        true,
      ),
    ).toBe(STATUS_TOPOLOGY_VISUAL.status.critical);
  });
});
