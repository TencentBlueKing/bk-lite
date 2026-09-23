import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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
        roles={buildChartRoleFields('line', (key) => key, false)}
        onRefreshFields={onRefreshFields}
      />
    </Form>
  );
};

describe('ChartRoleFieldsSection', () => {
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

  it('calls refresh once for the whole group', () => {
    const onRefreshFields = vi.fn();
    render(<Harness onRefreshFields={onRefreshFields} />);

    fireEvent.click(screen.getByText('dashboard.refreshFields'));
    expect(onRefreshFields).toHaveBeenCalledTimes(1);
  });
});
