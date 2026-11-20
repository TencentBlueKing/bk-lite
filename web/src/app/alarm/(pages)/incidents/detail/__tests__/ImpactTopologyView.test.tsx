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
    fireEvent.pointerDown(canvas, { button: 0, buttons: 1, pointerId: 1, clientX: 10, clientY: 20 });
    fireEvent.pointerMove(canvas, { buttons: 1, pointerId: 1, clientX: 46, clientY: 40 });
    fireEvent.pointerUp(canvas, { button: 0, buttons: 0, pointerId: 1 });
    expect(screen.getByTestId('impact-topology-graph').style.transform).toBe('translate(36px, 20px) scale(1)');
    expect(screen.queryByText('支付超时')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /web-01/ }));
    expect(screen.getByText('支付超时')).toBeTruthy();
  });

  it('drags one node away from its origin without opening alerts, and a later click still opens them', () => {
    renderView(
      <ImpactTopologyView
        alerts={[alarm({
          id: 1,
          title: '支付超时',
          monitor_objects: [{ monitor_id: 'm', cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
        })]}
        payload={{
          relation_status: 'ok',
          nodes: [{ inst_uuid: HOST, inst_name: 'web-01', layer: 'host', role: 'seed', found: true }],
          links: [],
        }}
      />,
    );
    const node = screen.getByRole('button', { name: /web-01/ }) as HTMLButtonElement;
    const before = node.style.left;
    fireEvent.pointerDown(node, { button: 0, buttons: 1, pointerId: 1, clientX: 10, clientY: 10 });
    fireEvent.pointerMove(node, { buttons: 1, pointerId: 1, clientX: 80, clientY: 46 });
    fireEvent.pointerUp(window, { button: 0, buttons: 0, pointerId: 1, clientX: 80, clientY: 46 });
    const moved = screen.getByRole('button', { name: /web-01/ }) as HTMLButtonElement;
    expect(moved.style.left).not.toBe(before);
    const parked = moved.style.left;
    fireEvent.pointerMove(window, { buttons: 0, pointerId: 1, clientX: 240, clientY: 180 });
    expect((screen.getByRole('button', { name: /web-01/ }) as HTMLButtonElement).style.left).toBe(parked);
    fireEvent.click(screen.getByRole('button', { name: /web-01/ }));
    expect(screen.queryByText('支付超时')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /web-01/ }));
    expect(screen.getByText('支付超时')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '关闭' }));
    expect(screen.queryByText('支付超时')).toBeNull();
  });

  it('zooms from the canvas controls and the wheel', () => {
    renderView(
      <ImpactTopologyView
        alerts={[alarm({
          id: 1,
          title: '主机告警',
          monitor_objects: [{ monitor_id: 'm', cmdb_id: HOST, resource_name: 'web-01' }],
        })]}
        payload={{
          relation_status: 'ok',
          nodes: [{ inst_uuid: HOST, inst_name: 'web-01', layer: 'host', role: 'seed', found: true }],
          links: [],
        }}
      />,
    );
    const shell = screen.getByTestId('impact-topology-shell') as HTMLElement & {
      requestFullscreen?: () => Promise<void>;
    };
    const requestFullscreen = vi.fn(() => Promise.resolve());
    shell.requestFullscreen = requestFullscreen;
    fireEvent.click(screen.getByRole('button', { name: '全屏' }));
    expect(requestFullscreen).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '放大' }));
    expect(screen.getByTestId('impact-topology-graph').style.transform).toContain('scale(1.15)');
    fireEvent.click(screen.getByRole('button', { name: '缩小' }));
    expect(screen.getByTestId('impact-topology-graph').style.transform).toContain('scale(1)');
    expect(screen.getByTestId('impact-topology-graph').style.transform).not.toContain('scale(1.15)');
    fireEvent.wheel(screen.getByTestId('impact-topology-canvas'), { deltaY: -120, clientX: 40, clientY: 40 });
    expect(screen.getByTestId('impact-topology-graph').style.transform).toContain('scale(1.1)');
  });

  it('draws every quiet object when the omitted hint is clicked', () => {
    const rack = '00000000-0000-4000-8000-000000000013';
    renderView(
      <ImpactTopologyView
        alerts={[alarm({
          id: 1,
          title: '主机告警',
          monitor_objects: [{ monitor_id: 'm', cmdb_id: HOST, resource_name: 'web-01' }],
        })]}
        payload={{
          relation_status: 'ok',
          quiet_omitted: 1,
          nodes: [{ inst_uuid: HOST, inst_name: 'web-01', layer: 'host', role: 'seed', found: true }],
          omitted_quiet_nodes: [{
            inst_uuid: rack,
            inst_name: 'rack-1',
            layer: 'infrastructure',
            role: 'related',
            found: true,
            alert_state: 'clear',
          }],
          omitted_quiet_links: [],
          links: [],
        }}
      />,
    );
    expect(screen.queryByRole('button', { name: /rack-1/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /入画请点击/ }));
    expect(screen.getByRole('button', { name: /rack-1/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /入画请点击/ })).toBeNull();
  });

  it('opens the alert query for an object that already has alerts', async () => {
    const loadAlerts = vi.fn(async () => ({
      count: 1,
      page: 1,
      page_size: 20,
      items: [{
        id: 7,
        alert_id: 'ALERT-7',
        title: '主机宕机',
        level: '1',
        status: 'pending',
        in_incident: true,
      }],
    }));
    renderView(
      <ImpactTopologyView
        alerts={[alarm({
          id: 1,
          title: '主机宕机',
          level: '1',
          monitor_objects: [{ monitor_id: 'm', cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
        })]}
        levels={[{ level_id: 1, level_display_name: '错误', color: '#ff7d00' } as never]}
        levelColors={{ 1: '#ff7d00' }}
        payload={{
          relation_status: 'ok',
          nodes: [{
            inst_uuid: HOST,
            inst_name: 'web-01',
            layer: 'host',
            role: 'seed',
            found: true,
            alert_state: 'incident',
            alert_count: 1,
            level: '1',
          }],
          links: [],
        }}
        loadAlerts={loadAlerts}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /web-01/ }));
    const link = await screen.findByRole('link', { name: '主机宕机' });
    expect(link.getAttribute('href')).toContain('alert_id=ALERT-7');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(screen.getByRole('columnheader', { name: '级别' })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: '状态' })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: '标题' })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: '归属' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: '本事故' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: '待响应' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: '错误' })).toBeTruthy();
    expect(loadAlerts).toHaveBeenCalledWith(HOST, 1);
  });

  it('loads a paged alert list for a related object and links to the existing alert page', async () => {
    const nic = '00000000-0000-4000-8000-000000000014';
    const loadAlerts = vi.fn(async (_instUuid: string, page: number) => ({
      count: 21,
      page,
      page_size: 20,
      items: [{ id: page, alert_id: `ALERT-${page}`, title: `第${page}页`, in_incident: false }],
    }));
    renderView(
      <ImpactTopologyView
        alerts={[alarm({
          id: 1,
          title: '主机告警',
          monitor_objects: [{ monitor_id: 'm', cmdb_id: HOST, resource_type: '主机', resource_name: 'web-01' }],
        })]}
        payload={{
          relation_status: 'ok',
          nodes: [
            { inst_uuid: HOST, inst_name: 'web-01', layer: 'host', role: 'seed', found: true },
            {
              inst_uuid: nic,
              inst_name: 'nic-1',
              layer: 'infrastructure',
              role: 'related',
              found: true,
              alert_state: 'clear',
            },
          ],
          links: [],
        }}
        loadAlerts={loadAlerts}
      />,
    );
    const related = screen.getByRole('button', { name: /nic-1/ }) as HTMLButtonElement;
    expect(related.dataset.alertState).toBe('clear');
    expect(related.style.borderStyle).toBe('solid');
    fireEvent.click(related);
    expect(await screen.findByRole('link', { name: '第1页' })).toBeTruthy();
    expect(screen.getByRole('link', { name: '第1页' }).getAttribute('href')).toContain('alert_id=ALERT-1');
    expect(screen.getByRole('link', { name: '第1页' }).getAttribute('target')).toBe('_blank');
    fireEvent.click(screen.getByTitle('Next Page'));
    expect(await screen.findByRole('link', { name: '第2页' })).toBeTruthy();
    expect(loadAlerts).toHaveBeenLastCalledWith(nic, 2);
  });
});
