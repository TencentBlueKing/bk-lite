import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { Form } from 'antd';

import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { reconcileComponentParamValue } from '@/app/ops-analysis/utils/componentParamSwitch';

const { getSourceDataByApiId } = vi.hoisted(() => ({
  getSourceDataByApiId: vi.fn(),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceList: vi.fn(async () => []),
    getSourceDataByApiId,
  }),
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: () => ({
      matches: false,
      media: '',
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      if (key === 'paramInput.dynamic.upstreamRequired') return '请先选择上游';
      if (key === 'paramInput.dynamic.invalidUpstream') return '查询入参无法对应到唯一的上游筛选';
      return key;
    },
  }),
}));

afterEach(() => {
  cleanup();
  getSourceDataByApiId.mockReset();
});

const regionParam: ParamItem = {
  name: 'cloud_region_ids',
  alias_name: '地域',
  type: 'string',
  filterType: 'params',
  value: null,
};

const zoneParam: ParamItem = {
  name: 'zone_id',
  alias_name: '可用区',
  type: 'string',
  filterType: 'params',
  value: null,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceId: 9,
      valueField: 'id',
      labelField: 'name',
      queryParams: { region_id: { ref: 'cloud_region_ids' } },
    },
  },
};

const dataSource = {
  id: 7,
  name: 'zones',
  params: [regionParam, zoneParam],
} as DatasourceItem;

const siteFilter: UnifiedFilterDefinition = {
  id: 'site_id__string',
  key: 'site_id',
  name: '机房',
  type: 'string',
  defaultValue: null,
  order: 0,
  enabled: true,
};

const followedSource = {
  id: 8,
  name: 'devices',
  params: [
    {
      name: 'site_id',
      alias_name: '机房',
      type: 'string',
      filterType: 'filter',
      value: 'local-room',
    },
    {
      name: 'device_id',
      alias_name: '设备',
      type: 'string',
      filterType: 'params',
      value: null,
      inputConfig: {
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceId: 12,
          valueField: 'id',
          labelField: 'name',
          queryParams: { room_id: { ref: 'site_id' } },
        },
      },
    },
  ],
} as DatasourceItem;

const QueryForm = ({
  source,
  initialParams,
  globalFilters = [],
  filterBindings,
  globalFilterValues,
  reconcile = false,
}: {
  source: DatasourceItem;
  initialParams: Record<string, unknown>;
  globalFilters?: UnifiedFilterDefinition[];
  filterBindings?: Record<string, boolean>;
  globalFilterValues?: Record<string, unknown>;
  reconcile?: boolean;
}) => {
  const [form] = Form.useForm();
  return (
    <Form form={form} initialValues={{ params: initialParams }}>
      <DataSourceParamsConfig
        selectedDataSource={source}
        includeFilterTypes={['params', 'fixed']}
        globalFilters={globalFilters}
        filterBindings={filterBindings}
        globalFilterValues={globalFilterValues as never}
        onParamOptionsResolved={reconcile ? (param, options) => {
          const current = form.getFieldValue(['params', param.name]);
          const next = reconcileComponentParamValue(current, options);
          if (next !== current) {
            form.setFieldValue(['params', param.name], next);
          }
        } : undefined}
      />
      <Form.Item shouldUpdate noStyle>
        {() => (
          <pre data-testid="form-params">{JSON.stringify(form.getFieldsValue(true)?.params ?? {})}</pre>
        )}
      </Form.Item>
    </Form>
  );
};

const regionInput = () => screen.getByRole('textbox');

describe('DataSourceParamsConfig options query', () => {
  it('blocks an empty upstream component param and reloads when it changes', async () => {
    getSourceDataByApiId.mockResolvedValue({
      data: [{ id: 'zone-1', name: '可用区1' }],
      warnings: [],
    });
    const view = render(
      <QueryForm source={dataSource} initialParams={{ cloud_region_ids: null, zone_id: null }} globalFilters={[]} />,
    );

    expect(await screen.findByText('请先选择上游')).not.toBeNull();
    expect(getSourceDataByApiId).not.toHaveBeenCalled();

    fireEvent.change(regionInput(), { target: { value: 'east' } });
    await waitFor(() => {
      expect(getSourceDataByApiId).toHaveBeenCalledWith(9, { region_id: 'east' }, undefined);
    });

    getSourceDataByApiId.mockClear();
    fireEvent.change(regionInput(), { target: { value: 'west' } });
    await waitFor(() => {
      expect(getSourceDataByApiId).toHaveBeenCalledWith(9, { region_id: 'west' }, undefined);
    });
    view.unmount();
  });

  it('follows a canvas filter when the binding key is absent and uses the form value when unbound', async () => {
    getSourceDataByApiId.mockResolvedValue({
      data: [{ id: 'dev-1', name: '设备1' }],
      warnings: [],
    });
    const view = render(
      <QueryForm
        source={followedSource}
        initialParams={{ site_id: 'typed-room', device_id: null }}
        globalFilters={[siteFilter]}
        filterBindings={{}}
        globalFilterValues={{ [siteFilter.id]: 'canvas-room' }}
      />,
    );
    await waitFor(() => {
      expect(getSourceDataByApiId).toHaveBeenCalledWith(12, { room_id: 'canvas-room' }, undefined);
    });
    view.unmount();

    getSourceDataByApiId.mockClear();
    render(
      <QueryForm
        source={followedSource}
        initialParams={{ site_id: 'typed-room', device_id: null }}
        globalFilters={[siteFilter]}
        filterBindings={{ [siteFilter.id]: false }}
        globalFilterValues={{ [siteFilter.id]: 'canvas-room' }}
      />,
    );
    await waitFor(() => {
      expect(getSourceDataByApiId).toHaveBeenCalledWith(12, { room_id: 'typed-room' }, undefined);
    });
  });

  it('keeps a still-valid value and clears an invalid one without selecting the first option', async () => {
    getSourceDataByApiId.mockImplementation(async (_id: number, params?: { region_id?: string }) => ({
      data: params?.region_id === 'east'
        ? [{ id: 'zone-keep', name: '保留' }, { id: 'zone-new', name: '新的' }]
        : [{ id: 'zone-new', name: '新的' }],
      warnings: [],
    }));
    render(
      <QueryForm
        source={dataSource}
        initialParams={{ cloud_region_ids: 'east', zone_id: 'zone-keep' }}
        globalFilters={[]}
        reconcile
      />,
    );

    await waitFor(() => {
      const params = JSON.parse(screen.getByTestId('form-params').textContent || '{}') as Record<string, unknown>;
      expect(params.zone_id).toBe('zone-keep');
    });
    expect(screen.queryByText('新的')).toBeNull();

    fireEvent.change(regionInput(), { target: { value: 'west' } });
    await waitFor(() => {
      const params = JSON.parse(screen.getByTestId('form-params').textContent || '{}') as Record<string, unknown>;
      expect(params.zone_id).toBeNull();
    });
    expect(screen.queryByText('新的')).toBeNull();
    expect(screen.queryByText('保留')).toBeNull();
  });

  it('keeps a stale value while options are loading and clears it when the list is empty', async () => {
    let finish: (value: { data: unknown[]; warnings: string[] }) => void = () => undefined;
    getSourceDataByApiId.mockImplementation(() => new Promise((resolve) => {
      finish = resolve;
    }));
    render(
      <QueryForm
        source={dataSource}
        initialParams={{ cloud_region_ids: 'east', zone_id: 'zone-stale' }}
        globalFilters={[]}
        reconcile
      />,
    );

    const readZone = () => JSON.parse(screen.getByTestId('form-params').textContent || '{}') as Record<string, unknown>;
    expect(readZone().zone_id).toBe('zone-stale');

    finish({ data: [], warnings: [] });
    await waitFor(() => {
      expect(readZone().zone_id).toBeNull();
    });
  });

  it('clears a stale value when the upstream is empty', async () => {
    render(
      <QueryForm
        source={dataSource}
        initialParams={{ cloud_region_ids: null, zone_id: 'zone-stale' }}
        globalFilters={[]}
        reconcile
      />,
    );

    expect(await screen.findByText('请先选择上游')).not.toBeNull();
    await waitFor(() => {
      const params = JSON.parse(screen.getByTestId('form-params').textContent || '{}') as Record<string, unknown>;
      expect(params.zone_id).toBeNull();
    });
    expect(getSourceDataByApiId).not.toHaveBeenCalled();
  });

  it('debounces a multiline upstream and blocks as soon as it is cleared', async () => {
    vi.useFakeTimers();
    getSourceDataByApiId.mockResolvedValue({
      data: [{ id: 'rack-1', name: '机柜1' }],
      warnings: [],
    });
    const source = {
      id: 11,
      name: 'racks',
      params: [
        {
          name: 'query',
          alias_name: '查询',
          type: 'string',
          filterType: 'params',
          value: null,
        },
        {
          name: 'rack_id',
          alias_name: '机柜',
          type: 'string',
          filterType: 'params',
          value: null,
          inputConfig: {
            control: 'select',
            optionsSource: {
              type: 'dynamic',
              sourceId: 15,
              valueField: 'id',
              labelField: 'name',
              queryParams: { keyword: { ref: 'query' } },
            },
          },
        },
      ],
    } as DatasourceItem;

    try {
      render(
        <QueryForm
          source={source}
          initialParams={{ query: '', rack_id: null }}
          globalFilters={[]}
        />,
      );
      expect(screen.getByText('请先选择上游')).not.toBeNull();
      const query = screen.getByRole('textbox');
      fireEvent.change(query, { target: { value: '机' } });
      fireEvent.change(query, { target: { value: '机柜' } });
      expect(query).toHaveProperty('value', '机柜');
      expect(getSourceDataByApiId).not.toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(299);
      });
      expect(getSourceDataByApiId).not.toHaveBeenCalled();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1);
      });
      expect(getSourceDataByApiId).toHaveBeenCalledTimes(1);
      expect(getSourceDataByApiId).toHaveBeenCalledWith(15, { keyword: '机柜' }, undefined);

      fireEvent.change(query, { target: { value: '机柜2' } });
      fireEvent.change(query, { target: { value: '' } });
      expect(query).toHaveProperty('value', '');
      expect(screen.getByText('请先选择上游')).not.toBeNull();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      expect(getSourceDataByApiId).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('debounces a number upstream one trailing request', async () => {
    vi.useFakeTimers();
    getSourceDataByApiId.mockResolvedValue({
      data: [{ id: 'rack-1', name: '机柜1' }],
      warnings: [],
    });
    const source = {
      id: 12,
      name: 'by-limit',
      params: [
        {
          name: 'limit',
          alias_name: '数量',
          type: 'number',
          filterType: 'params',
          value: null,
        },
        {
          name: 'rack_id',
          alias_name: '机柜',
          type: 'string',
          filterType: 'params',
          value: null,
          inputConfig: {
            control: 'select',
            optionsSource: {
              type: 'dynamic',
              sourceId: 16,
              valueField: 'id',
              labelField: 'name',
              queryParams: { limit: { ref: 'limit' } },
            },
          },
        },
      ],
    } as DatasourceItem;

    try {
      render(
        <QueryForm
          source={source}
          initialParams={{ limit: null, rack_id: null }}
          globalFilters={[]}
        />,
      );
      const limit = screen.getByRole('spinbutton');
      fireEvent.change(limit, { target: { value: '4' } });
      fireEvent.change(limit, { target: { value: '12' } });
      expect(getSourceDataByApiId).not.toHaveBeenCalled();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      expect(getSourceDataByApiId).toHaveBeenCalledTimes(1);
      expect(getSourceDataByApiId).toHaveBeenCalledWith(16, { limit: 12 }, undefined);
    } finally {
      vi.useRealTimers();
    }
  });

  it('reloads immediately when an upstream radio is selected', async () => {
    vi.useFakeTimers();
    getSourceDataByApiId.mockResolvedValue({
      data: [{ id: 'rack-1', name: '机柜1' }],
      warnings: [],
    });
    const source = {
      id: 13,
      name: 'by-area',
      params: [
        {
          name: 'area_id',
          alias_name: '分区',
          type: 'string',
          filterType: 'params',
          value: null,
          inputConfig: {
            control: 'radio',
            optionsSource: {
              type: 'static',
              staticItems: [
                { label: '一区', value: 'a1' },
                { label: '二区', value: 'a2' },
              ],
            },
          },
        },
        {
          name: 'rack_id',
          alias_name: '机柜',
          type: 'string',
          filterType: 'params',
          value: null,
          inputConfig: {
            control: 'select',
            optionsSource: {
              type: 'dynamic',
              sourceId: 17,
              valueField: 'id',
              labelField: 'name',
              queryParams: { area_id: { ref: 'area_id' } },
            },
          },
        },
      ],
    } as DatasourceItem;

    try {
      render(
        <QueryForm
          source={source}
          initialParams={{ area_id: null, rack_id: null }}
          globalFilters={[]}
        />,
      );
      expect(getSourceDataByApiId).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole('radio', { name: '二区' }));
      await act(async () => {
        await Promise.resolve();
      });
      expect(getSourceDataByApiId).toHaveBeenCalledTimes(1);
      expect(getSourceDataByApiId).toHaveBeenCalledWith(17, { area_id: 'a2' }, undefined);
    } finally {
      vi.useRealTimers();
    }
  });
});
