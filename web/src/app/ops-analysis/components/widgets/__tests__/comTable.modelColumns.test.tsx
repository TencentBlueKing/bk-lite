// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ComTable from '@/app/ops-analysis/components/widgets/comTable';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => (key === 'dashboard.selectModel' ? '请选择模型' : key),
  }),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
});

afterEach(() => {
  cleanup();
});

const simulatedPayload = {
  items: [
    {
      inst_name: 'web-1',
      cpu: 0,
      enabled: false,
      status: '1',
      status_display: '运行中',
      organization: [7],
      organization_display: '研发',
      owner: 'user-9',
      extra: { port: 80 },
      password: 'secret-value',
    },
  ],
  count: 1,
};

const dataSource = {
  rest_api: 'cmdb/query_cmdb_instances',
  params: [{ name: 'page' }, { name: 'page_size' }, { name: 'model_id' }],
  field_schema: [
    { key: 'inst_name', title: '实例名称' },
    { key: 'name', title: '名称', table: false },
    { key: 'status', title: '结果状态', table: false },
  ],
} as any;

describe('ComTable model attribute columns', () => {
  it('renders the saved columns and the raw cell text', () => {
    render(
      <div style={{ width: 900, height: 480 }}>
        <ComTable
          rawData={simulatedPayload}
          loading={false}
          dataSource={dataSource}
          config={{
            chartType: 'table',
            params: { model_id: 'host' },
            tableConfig: {
              columns: [
                { key: 'inst_name', title: '实例名称', visible: true, order: 0 },
                { key: 'cpu', title: 'CPU', visible: true, order: 1 },
                { key: 'status', title: '状态', visible: true, order: 2 },
              ],
            },
          }}
        />
      </div>,
    );

    expect(screen.getByText('实例名称')).toBeTruthy();
    expect(screen.getByText('CPU')).toBeTruthy();
    expect(screen.getByText('状态')).toBeTruthy();
    expect(screen.getByText('web-1')).toBeTruthy();
    expect(screen.getByText('0')).toBeTruthy();
    expect(screen.getAllByText('1').length).toBeGreaterThan(0);
    expect(screen.queryByText('运行中')).toBeNull();
  });

  it('keeps headers when the simulated page is empty and prompts before a model is chosen', () => {
    const { rerender } = render(
      <div style={{ width: 900, height: 480 }}>
        <ComTable
          rawData={{ ...simulatedPayload, items: [], count: 0 }}
          loading={false}
          dataSource={dataSource}
          config={{
            chartType: 'table',
            params: { model_id: 'host' },
            tableConfig: { columns: [] },
          }}
        />
      </div>,
    );

    expect(screen.getByText('实例名称')).toBeTruthy();
    expect(screen.getByText('名称')).toBeTruthy();
    expect(screen.getByText('结果状态')).toBeTruthy();
    expect(screen.queryByText('请选择模型')).toBeNull();

    rerender(
      <div style={{ width: 900, height: 480 }}>
        <ComTable
          rawData={{ items: [], count: 0 }}
          loading={false}
          dataSource={dataSource}
          config={{ chartType: 'table', params: {}, tableConfig: { columns: [] } }}
        />
      </div>,
    );

    expect(screen.getByText('请选择模型')).toBeTruthy();
    expect(screen.getByText('实例名称')).toBeTruthy();
    expect(screen.getByText('名称')).toBeTruthy();
    expect(screen.getByText('结果状态')).toBeTruthy();
  });

  it('leaves an older source on its configured text, including 0', () => {
    render(
      <ComTable
        rawData={{ items: [{ name: '甲', value: 0, status: 'active' }], count: 1 }}
        loading={false}
        dataSource={{
          rest_api: 'monitor/query_monitor_instances',
          field_schema: [
            { key: 'name', title: '名称' },
            { key: 'value', title: '值', table: false },
            { key: 'status', title: '状态' },
          ],
        } as any}
        config={{
          chartType: 'table',
          tableConfig: {
            columns: [
              { key: 'name', title: '名称', visible: true, order: 0 },
              { key: 'value', title: '值', visible: true, order: 1 },
              { key: 'status', title: '状态', visible: true, order: 2 },
            ],
          },
        }}
      />
    );

    expect(screen.getByText('名称')).toBeTruthy();
    expect(screen.getByText('值')).toBeTruthy();
    expect(screen.getByText('状态')).toBeTruthy();
    expect(screen.getByText('甲')).toBeTruthy();
    expect(screen.getByText('0')).toBeTruthy();
    expect(screen.getByText('active')).toBeTruthy();
    expect(screen.queryByText('NO')).toBeNull();
  });
});
