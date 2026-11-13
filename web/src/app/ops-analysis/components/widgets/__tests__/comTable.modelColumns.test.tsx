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
  column_fields: {
    source: 'model_attrs',
    model_key: 'host',
    fields: [
      { key: 'inst_name', title: '实例名称', attr_type: 'str', default_visible: true },
      { key: 'cpu', title: 'CPU', attr_type: 'int', default_visible: true },
      { key: 'enabled', title: '是否启用', attr_type: 'bool', default_visible: true },
      {
        key: 'status',
        title: '运行状态',
        attr_type: 'enum',
        default_visible: true,
        display_key: 'status_display',
        options: [{ value: '1', label: '运行中' }, { value: '0', label: '停止' }],
      },
      {
        key: 'organization',
        title: '组织',
        attr_type: 'organization',
        default_visible: true,
        display_key: 'organization_display',
      },
      { key: 'owner', title: '负责人', attr_type: 'user', default_visible: true, display_key: 'owner_display' },
      { key: 'extra', title: '扩展', attr_type: 'table', default_visible: true },
      { key: 'inst_uuid', title: '实例标识', attr_type: 'str', default_visible: false },
    ],
  },
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
  it('renders Chinese headers and typed cells from simulated model metadata', () => {
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
              columnModelKey: 'app',
              columns: [
                { key: 'status', title: '旧模型的状态', visible: true, order: 0 },
                { key: 'name', title: '名称', visible: true, order: 1 },
                { key: 'password', title: '密码', visible: true, order: 2 },
              ],
            },
          }}
        />
      </div>,
    );

    expect(screen.getByText('实例名称')).toBeTruthy();
    expect(screen.getByText('运行状态')).toBeTruthy();
    expect(screen.queryByText('旧模型的状态')).toBeNull();
    expect(screen.queryByText('名称')).toBeNull();
    expect(screen.queryByText('密码')).toBeNull();
    expect(screen.queryByText('结果状态')).toBeNull();
    expect(screen.getByText('web-1')).toBeTruthy();
    expect(screen.getByText('0')).toBeTruthy();
    expect(screen.getByText('NO')).toBeTruthy();
    expect(screen.getByText('运行中')).toBeTruthy();
    expect(screen.getByText('研发')).toBeTruthy();
    expect(screen.getByText('user-9')).toBeTruthy();
    expect(screen.getByText('{"port":80}')).toBeTruthy();
    expect(screen.queryByText('[object Object]')).toBeNull();
    expect(screen.queryByText('secret-value')).toBeNull();
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
            tableConfig: { columnModelKey: 'host', columns: [] },
          }}
        />
      </div>,
    );

    expect(screen.getByText('运行状态')).toBeTruthy();
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
    expect(screen.queryByText('名称')).toBeNull();
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
