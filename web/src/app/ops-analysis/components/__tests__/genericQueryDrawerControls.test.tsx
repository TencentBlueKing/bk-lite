import React, { useEffect, useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { getDataSourceFormParamInitialValue } from '@/app/ops-analysis/utils/dataSourceFormParams';
import { processDataSourceParams } from '@/app/ops-analysis/utils/widgetDataTransform';

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceList: vi.fn(async () => []),
    getSourceDataByApiId: vi.fn(async () => ({ data: [] })),
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
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

afterEach(cleanup);

const source = {
  id: 54,
  name: 'CMDB 模型通用查询',
  rest_api: 'cmdb/query_cmdb_models',
  params: [
    {
      name: 'analysis_mode',
      alias_name: '分析方式',
      type: 'string',
      filterType: 'params',
      value: 'detail',
      required: true,
      inputConfig: {
        control: 'select',
        optionsSource: {
          type: 'static',
          staticItems: [
            { label: '明细', value: 'detail', charts: ['table'], result: { structure: 'table' } },
            { label: '计数', value: 'count', charts: ['single'], result: { structure: 'value' } },
            { label: '分布', value: 'distribution', charts: ['bar', 'pie', 'topN'], result: { structure: 'category' } },
          ],
        },
      },
    },
    {
      name: 'model_id',
      alias_name: '模型',
      type: 'string',
      filterType: 'params',
      value: '',
    },
    {
      name: 'page',
      alias_name: '页码',
      type: 'number',
      filterType: 'params',
      value: null,
    },
    {
      name: 'page_size',
      alias_name: '每页条数',
      type: 'number',
      filterType: 'params',
      value: null,
    },
  ] as ParamItem[],
} as DatasourceItem;

const Drawer = () => {
  const [form] = Form.useForm();
  const [chartType, setChartType] = useState('table');
  const analysisMode = Form.useWatch(['params', 'analysis_mode'], { form, preserve: true });
  const page = Form.useWatch(['params', 'page'], { form, preserve: true });
  const pageSize = Form.useWatch(['params', 'page_size'], { form, preserve: true });
  useEffect(() => {
    const params: Record<string, unknown> = {};
    source.params?.forEach((param) => {
      params[param.name] = getDataSourceFormParamInitialValue(param);
    });
    form.setFieldsValue({ chartType: 'table', params });
  }, [form]);
  const switchChart = (next: string) => {
    setChartType(next);
    form.setFieldValue('chartType', next);
  };
  const request = processDataSourceParams({
    sourceParams: source.params,
    definitionParams: source.params,
    userParams: {
      analysis_mode: analysisMode,
      page,
      page_size: pageSize,
    },
    chartType,
  });
  return (
    <div style={{ width: 320 }}>
      <Form form={form} layout="vertical">
        <button type="button" onClick={() => switchChart('single')}>切到单值</button>
        <button type="button" onClick={() => switchChart('bar')}>切到柱状</button>
        <button type="button" onClick={() => switchChart('pie')}>切到饼图</button>
        <button type="button" onClick={() => switchChart('topN')}>切到排行榜</button>
        <button type="button" onClick={() => switchChart('table')}>切到表格</button>
        <div data-testid="chart-type">{chartType}</div>
        <div data-testid="saved-mode">{String(analysisMode ?? '')}</div>
        <div data-testid="request">{JSON.stringify(request)}</div>
        <DataSourceParamsConfig selectedDataSource={source} />
      </Form>
    </div>
  );
};

describe('generic query config drawer', () => {
  it('shows analysis mode and paging on every chart and does not change them when switching', async () => {
    render(<Drawer />);
    await waitFor(() => {
      expect(screen.getByText('分析方式')).toBeTruthy();
      expect(screen.getByText('模型')).toBeTruthy();
      expect(screen.getByText('页码')).toBeTruthy();
      expect(screen.getByText('每页条数')).toBeTruthy();
    });
    expect(screen.queryByText('统计内容')).toBeNull();
    expect(screen.queryByText('展示前几名')).toBeNull();
    const numbers = screen.getAllByRole('spinbutton') as HTMLInputElement[];
    expect(numbers).toHaveLength(2);
    expect(numbers.map((node) => node.value)).toEqual(['', '']);
    expect(screen.getByTestId('saved-mode').textContent).toBe('detail');
    expect(JSON.parse(screen.getByTestId('request').textContent || '{}')).toEqual({
      analysis_mode: 'detail',
    });

    const mode = screen.getByRole('combobox');
    fireEvent.mouseDown(mode);
    fireEvent.click(await screen.findByText('计数'));
    await waitFor(() => {
      expect(screen.getByTestId('saved-mode').textContent).toBe('count');
    });

    for (const name of ['切到单值', '切到柱状', '切到饼图', '切到排行榜', '切到表格']) {
      fireEvent.click(screen.getByRole('button', { name }));
      await waitFor(() => {
        expect(screen.getByTestId('saved-mode').textContent).toBe('count');
      });
      expect(screen.getByText('页码')).toBeTruthy();
      expect(screen.getByText('每页条数')).toBeTruthy();
      expect(JSON.parse(screen.getByTestId('request').textContent || '{}').analysis_mode).toBe('count');
      expect(JSON.parse(screen.getByTestId('request').textContent || '{}').page).toBeUndefined();
    }
  });
});
