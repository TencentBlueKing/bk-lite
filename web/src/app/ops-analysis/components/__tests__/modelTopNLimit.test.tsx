import React, { useEffect, useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Button, Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { processDataSourceParams } from '@/app/ops-analysis/utils/widgetDataTransform';

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceList: vi.fn(async () => []),
    getSourceDataByApiId: vi.fn(async () => ({ data: [] })),
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
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
  params: [
    {
      name: 'analysis_mode',
      alias_name: '分析方式',
      type: 'string',
      filterType: 'params',
      value: 'distribution',
      inputConfig: {
        control: 'select',
        optionsSource: {
          type: 'static',
          staticItems: [
            { label: '明细', value: 'detail' },
            { label: '计数', value: 'count' },
            { label: '分布', value: 'distribution' },
          ],
        },
      },
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

const Harness = () => {
  const [form] = Form.useForm();
  const [chartType, setChartType] = useState('topN');
  const pageSize = Form.useWatch(['params', 'page_size'], { form, preserve: true });
  useEffect(() => {
    form.setFieldsValue({
      chartType: 'topN',
      params: { analysis_mode: 'distribution', page: null, page_size: 10 },
    });
  }, [form]);
  const request = processDataSourceParams({
    sourceParams: source.params,
    userParams: form.getFieldsValue(true)?.params,
    chartType,
  });
  return (
    <Form form={form} layout="vertical">
      <DataSourceParamsConfig selectedDataSource={source} />
      <Button onClick={() => {
        setChartType('bar');
        form.setFieldValue('chartType', 'bar');
      }}
      >
        切到柱状图
      </Button>
      <Button onClick={() => {
        setChartType('pie');
        form.setFieldValue('chartType', 'pie');
      }}
      >
        切到饼图
      </Button>
      <div data-testid="page-size">{pageSize === undefined || pageSize === null ? '' : String(pageSize)}</div>
      <div data-testid="request">{JSON.stringify(request)}</div>
    </Form>
  );
};

describe('model paging stays on ranking, bar and pie', () => {
  it('keeps the page size when the chart changes and omits it after clearing', async () => {
    render(<Harness />);
    const inputs = await screen.findAllByRole('spinbutton');
    expect(screen.queryByText('展示前几名')).toBeNull();
    expect(inputs).toHaveLength(2);
    expect((inputs[1] as HTMLInputElement).value).toBe('10');

    fireEvent.click(screen.getByRole('button', { name: '切到柱状图' }));
    await waitFor(() => {
      expect(screen.getByTestId('page-size').textContent).toBe('10');
    });
    expect(JSON.parse(screen.getByTestId('request').textContent || '{}').page_size).toBe(10);
    expect(JSON.parse(screen.getByTestId('request').textContent || '{}').analysis_mode).toBe('distribution');

    fireEvent.click(screen.getByRole('button', { name: '切到饼图' }));
    const pieInputs = screen.getAllByRole('spinbutton');
    fireEvent.change(pieInputs[1], { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('page-size').textContent).toBe('');
    });
    const request = JSON.parse(screen.getByTestId('request').textContent || '{}');
    expect(request.page_size).toBeUndefined();
    expect(request.analysis_mode).toBe('distribution');
  });
});
