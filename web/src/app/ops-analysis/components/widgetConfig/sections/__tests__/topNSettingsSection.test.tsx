import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import React from 'react';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { TopNSettingsSection } from '../topNSettingsSection';

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
  selectedDataSource = { id: 1 } as DatasourceItem,
  options = [] as Array<{ label: string; value: string }>,
  loadingFields = false,
  onRefreshFields = () => undefined,
}: {
  selectedDataSource?: DatasourceItem;
  options?: Array<{ label: string; value: string }>;
  loadingFields?: boolean;
  onRefreshFields?: () => void;
}) => {
  const [form] = Form.useForm();

  return (
    <Form form={form}>
      <TopNSettingsSection
        t={(key) => key}
        selectedDataSource={selectedDataSource}
        topNLabelFieldOptions={options}
        topNValueFieldOptions={options}
        loadingFields={loadingFields}
        onRefreshFields={onRefreshFields}
      />
    </Form>
  );
};

describe('TopNSettingsSection field refresh', () => {
  it('shows refresh button and empty dropdowns without no-available-fields copy', () => {
    render(<Harness options={[]} />);

    expect(screen.getAllByText('dashboard.refreshFields')).toHaveLength(1);
    expect(screen.queryByText('topology.nodeConfig.noAvailableFields')).toBeNull();
    expect(screen.getAllByText('topology.nodeConfig.clickRefreshToGetFields').length).toBeGreaterThan(0);
    expect(screen.getByText('topology.nodeConfig.displayField')).toBeTruthy();
    expect(screen.getByText('topology.nodeConfig.valueField')).toBeTruthy();
    expect(document.querySelectorAll('.cursor-help').length).toBeGreaterThan(0);
  });

  it('calls onRefreshFields when refresh is clicked', () => {
    const onRefreshFields = vi.fn();
    render(<Harness onRefreshFields={onRefreshFields} />);

    fireEvent.click(screen.getByText('dashboard.refreshFields'));
    expect(onRefreshFields).toHaveBeenCalledTimes(1);
  });
});
