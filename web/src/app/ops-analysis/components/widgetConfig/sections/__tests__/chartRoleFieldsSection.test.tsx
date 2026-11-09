import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import React, { useEffect } from 'react';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { ChartRoleFieldsSection, buildChartRoleFields } from '../chartRoleFieldsSection';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
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

const Harness = ({
  onReady,
  options = [],
  onRefreshFields = () => undefined,
}: {
  onReady?: (form: ReturnType<typeof Form.useForm>[0]) => void;
  options?: Array<{ label: string; value: string }>;
  onRefreshFields?: () => void;
}) => {
  const [form] = Form.useForm();
  useEffect(() => {
    onReady?.(form);
  }, [form, onReady]);

  return (
    <Form form={form}>
      <ChartRoleFieldsSection
        t={(key) => key}
        selectedDataSource={{ id: 1 } as DatasourceItem}
        options={options}
        roles={buildChartRoleFields('pie', (key) => key, false)}
        onRefreshFields={onRefreshFields}
      />
    </Form>
  );
};

describe('ChartRoleFieldsSection', () => {
  it('exposes category, values, and series for line and bar', () => {
    const t = (key: string) => key;
    const line = buildChartRoleFields('line', t, false);
    const bar = buildChartRoleFields('bar', t, false);
    expect(line.map((role) => role.name)).toEqual([
      'dimensionField',
      'valueFields',
      'seriesField',
    ]);
    expect(bar.map((role) => [role.name, role.multiple || false, role.optionScope])).toEqual([
      ['dimensionField', false, 'all'],
      ['valueFields', true, 'values'],
      ['seriesField', false, 'series'],
    ]);
    expect(line.map((role) => role.label)).toEqual([
      'dashboard.lineBarCategoryField',
      'dashboard.lineBarValueFields',
      'dashboard.lineBarSeriesField',
    ]);
    expect(buildChartRoleFields('pie', t, false).map((role) => role.name)).toEqual([
      'dimensionField',
      'valueField',
    ]);
  });

  it('shows one refresh button, role tips, and the empty-list hint', () => {
    render(<Harness />);

    expect(screen.getAllByText('dashboard.refreshFields')).toHaveLength(1);
    expect(screen.getAllByText('topology.nodeConfig.clickRefreshToGetFields').length).toBeGreaterThan(0);
    expect(document.querySelectorAll('.cursor-help').length).toBe(2);
  });

  it('does not show name or value until the user selects them', () => {
    let formApi: ReturnType<typeof Form.useForm>[0] | undefined;
    render(
      <Harness
        options={[
          { label: 'name', value: 'name' },
          { label: 'value', value: 'value' },
        ]}
        onReady={(form) => {
          formApi = form;
        }}
      />,
    );

    expect(formApi?.getFieldValue('dimensionField')).toBeUndefined();
    expect(formApi?.getFieldValue('valueField')).toBeUndefined();
    expect(screen.queryByText('name')).toBeNull();
    expect(screen.queryByText('value')).toBeNull();
  });

  it('locks and clears series when several value fields are selected', () => {
    let formApi: ReturnType<typeof Form.useForm>[0] | undefined;
    const Ready = () => {
      const [form] = Form.useForm();
      useEffect(() => {
        formApi = form;
        form.setFieldsValue({
          dimensionField: 'time',
          valueFields: ['cpu', 'mem'],
          seriesField: 'host',
        });
      }, [form]);
      return (
        <Form form={form}>
          <ChartRoleFieldsSection
            t={(key) => key}
            selectedDataSource={{ id: 1 } as DatasourceItem}
            options={[
              { label: 'time', value: 'time' },
              { label: 'cpu', value: 'cpu' },
              { label: 'mem', value: 'mem' },
              { label: 'host', value: 'host' },
            ]}
            valueOptions={[
              { label: 'cpu', value: 'cpu' },
              { label: 'mem', value: 'mem' },
            ]}
            roles={buildChartRoleFields('line', (key) => key, false)}
            onRefreshFields={() => undefined}
          />
        </Form>
      );
    };
    render(<Ready />);

    expect(document.querySelectorAll('.ant-select-multiple')).toHaveLength(1);
    expect(document.querySelectorAll('.ant-select-disabled')).toHaveLength(1);
    expect(formApi?.getFieldValue('seriesField')).toBeUndefined();
  });

  it('clears series after it is set to the same field as the category', async () => {
    let formApi: ReturnType<typeof Form.useForm>[0] | undefined;
    const Ready = () => {
      const [form] = Form.useForm();
      useEffect(() => {
        formApi = form;
      }, [form]);
      return (
        <Form
          form={form}
          initialValues={{ dimensionField: 'host', valueFields: ['cpu'] }}
        >
          <ChartRoleFieldsSection
            t={(key) => key}
            selectedDataSource={{ id: 1 } as DatasourceItem}
            options={[
              { label: 'host', value: 'host' },
              { label: 'cpu', value: 'cpu' },
            ]}
            valueOptions={[{ label: 'cpu', value: 'cpu' }]}
            roles={buildChartRoleFields('line', (key) => key, false)}
            onRefreshFields={() => undefined}
          />
        </Form>
      );
    };
    render(<Ready />);

    await act(async () => {
      formApi?.setFieldsValue({ seriesField: 'host' });
    });
    await waitFor(() => {
      expect(formApi?.getFieldValue('seriesField')).toBeUndefined();
    });

    await act(async () => {
      formApi?.setFieldsValue({ seriesField: 'cpu' });
    });
    await waitFor(() => {
      expect(formApi?.getFieldValue('seriesField')).toBeUndefined();
    });
  });

  it('keeps only refresh beside the data-fields title and a multi-select for values', () => {
    render(
      <Form>
        <ChartRoleFieldsSection
          t={(key) => key}
          selectedDataSource={{ id: 1 } as DatasourceItem}
          options={[
            { label: 'time', value: 'time' },
            { label: 'cpu', value: 'cpu' },
            { label: 'host', value: 'host' },
          ]}
          valueOptions={[{ label: 'cpu', value: 'cpu' }]}
          roles={buildChartRoleFields('line', (key) => key, false)}
          onRefreshFields={() => undefined}
        />
      </Form>,
    );

    expect(screen.getByText('dashboard.dataFields')).toBeTruthy();
    expect(screen.getAllByText('dashboard.refreshFields')).toHaveLength(1);
    expect(screen.queryByText('dashboard.lineBarRestoreRecommended')).toBeNull();
    expect(screen.queryByText('恢复推荐')).toBeNull();
    expect(document.querySelectorAll('.ant-select-multiple')).toHaveLength(1);
    expect(document.querySelectorAll('.ant-select')).toHaveLength(3);
  });

  it('calls refresh once for the whole group', () => {
    const onRefreshFields = vi.fn();
    render(<Harness onRefreshFields={onRefreshFields} />);

    fireEvent.click(screen.getByText('dashboard.refreshFields'));
    expect(onRefreshFields).toHaveBeenCalledTimes(1);
  });
});
