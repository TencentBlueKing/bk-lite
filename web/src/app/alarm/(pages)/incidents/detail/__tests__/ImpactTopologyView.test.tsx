import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import type { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import ImpactTopologyView from '../ImpactTopologyView';

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: {
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
    },
  };
});

afterEach(cleanup);

beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
});

const HOST = '00000000-0000-4000-8000-000000000001';

function renderView(node: React.ReactElement) {
  return render(<IntlProvider locale="zh" messages={{}}>{node}</IntlProvider>);
}

function alarm(partial: Partial<AlarmTableDataItem> & Pick<AlarmTableDataItem, 'id' | 'title'>): AlarmTableDataItem {
  return {
    event_count: 9,
    duration: '',
    operator_user: '',
    operator: [],
    created_at: '',
    updated_at: '',
    closed_at: null,
    alert_id: String(partial.id),
    status: 'open',
    level: '0',
    content: '',
    first_event_time: null,
    last_event_time: null,
    item: '',
    resource_id: '',
    resource_name: '',
    resource_type: '',
    operate: null,
    ...partial,
  };
}

describe('ImpactTopologyView', () => {
  it('explains a missing cmdb purchase and does not draw nodes or toast', async () => {
    const antd = await import('antd');
    renderView(
      <ImpactTopologyView
        alerts={[alarm({
          id: 1,
          title: '支付超时',
          monitor_objects: [{ monitor_id: 'm', cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
        })]}
        payload={{ relation_status: 'not_purchased', message: '未购买 CMDB，无法按配置关系展示影响拓扑' }}
      />,
    );
    expect(screen.getByRole('status').textContent || '').toContain('未购买 CMDB');
    expect(screen.queryByRole('button', { name: /web-01/ })).toBeNull();
    expect(antd.message.error).not.toHaveBeenCalled();
  });

  it('shows the snapshot when relations are unavailable and ignores a bridge from the payload', async () => {
    const antd = await import('antd');
    renderView(
      <ImpactTopologyView
        alerts={[alarm({
          id: 1,
          title: '支付超时',
          level: '1',
          monitor_objects: [{ monitor_id: 'm', cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
        })]}
        levels={[{ level_id: 1, level_display_name: '警告', color: '#ffaa00' } as never]}
        levelColors={{ 1: '#ffaa00' }}
        payload={{
          relation_status: 'unavailable',
          message: '配置关系暂时查不到',
          nodes: [{ inst_uuid: 'bridge', inst_name: '支付中台', role: 'bridge', found: true }],
          links: [],
        }}
      />,
    );
    expect(screen.getByRole('status').textContent || '').toContain('配置关系暂时查不到');
    expect(screen.getByRole('button', { name: /web-01/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /支付中台/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /web-01/ }));
    expect(screen.getByText('支付超时')).toBeTruthy();
    expect(antd.message.error).not.toHaveBeenCalled();
  });

  it('opens the side panel for the merged alert object', () => {
    renderView(
      <ImpactTopologyView
        alerts={[
          alarm({
            id: 1,
            title: '超时',
            level: '2',
            monitor_objects: [{ monitor_id: 'm1', cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
          }),
          alarm({
            id: 2,
            title: '宕机',
            level: '0',
            monitor_objects: [{ monitor_id: 'm2', cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
          }),
        ]}
        levels={[
          { level_id: 0, level_display_name: '严重', color: '#aa0000' } as never,
          { level_id: 2, level_display_name: '警告', color: '#ffaa00' } as never,
        ]}
        levelColors={{ 0: '#aa0000', 2: '#ffaa00' }}
        payload={{
          relation_status: 'ok',
          nodes: [{ inst_uuid: HOST, inst_name: 'web-01', layer: 'host', role: 'seed', found: true }],
          links: [],
        }}
      />,
    );
    const button = screen.getByRole('button', { name: /web-01/ }) as HTMLButtonElement;
    expect(button.textContent || '').toContain('2 条告警');
    expect(button.style.borderColor).toBe('rgb(170, 0, 0)');
    expect(button.style.backgroundColor).toContain('#aa0000');
    fireEvent.click(button);
    expect(button.style.boxShadow).toContain('#aa0000');
    expect(button.style.boxShadow).not.toContain('primary');
    expect(button.style.borderStyle).toBe('solid');
    expect(screen.getByText('超时')).toBeTruthy();
    expect(screen.getByText('宕机')).toBeTruthy();
  });

  it('paints bridge and unbound nodes with the prototype colors', () => {
    const bridge = '00000000-0000-4000-8000-000000000002';
    renderView(
      <ImpactTopologyView
        alerts={[
          alarm({
            id: 1,
            title: '超时',
            level: '0',
            monitor_objects: [{ monitor_id: 'm1', cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
          }),
          alarm({
            id: 2,
            title: '未绑定告警',
            resource_name: '裸告警',
            monitor_objects: [],
          }),
        ]}
        levels={[{ level_id: 0, level_display_name: '严重', color: '#aa0000' } as never]}
        levelColors={{ 0: '#aa0000' }}
        payload={{
          relation_status: 'ok',
          nodes: [
            { inst_uuid: HOST, inst_name: 'web-01', layer: 'host', role: 'seed', found: true },
            { inst_uuid: bridge, inst_name: '支付中台', layer: 'service', role: 'bridge', found: true },
          ],
          links: [],
        }}
      />,
    );
    const bridgeButton = screen.getByRole('button', { name: /支付中台/ }) as HTMLButtonElement;
    expect(bridgeButton.style.borderColor).toBe('rgb(123, 225, 136)');
    expect(bridgeButton.style.backgroundColor).toBe('rgb(240, 255, 241)');
    expect(bridgeButton.style.borderStyle).toBe('dashed');
    const unbound = screen.getByRole('button', { name: /裸告警/ }) as HTMLButtonElement;
    expect(unbound.style.borderColor).toBe('rgb(201, 205, 212)');
    expect(unbound.style.backgroundColor).toBe('rgb(242, 243, 245)');
  });

  it('pans the whole graph and keeps a click from opening the side panel', () => {
    renderView(
      <ImpactTopologyView
        alerts={[alarm({
          id: 1,
          title: '支付超时',
          monitor_objects: [{ monitor_id: 'm', cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
        })]}
        levels={[{ level_id: 0, level_display_name: '严重', color: '#aa0000' } as never]}
        levelColors={{ 0: '#aa0000' }}
        payload={{
          relation_status: 'ok',
          nodes: [{ inst_uuid: HOST, inst_name: 'web-01', layer: 'host', role: 'seed', found: true }],
          links: [],
        }}
      />,
    );
    const canvas = screen.getByTestId('impact-topology-canvas');
    fireEvent.pointerDown(canvas, { button: 0, pointerId: 1, clientX: 10, clientY: 20 });
    fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 46, clientY: 40 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    expect(screen.getByTestId('impact-topology-graph').style.transform).toBe('translate(36px, 20px)');
    fireEvent.click(screen.getByRole('button', { name: /web-01/ }));
    expect(screen.queryByText('支付超时')).toBeNull();
  });
});
