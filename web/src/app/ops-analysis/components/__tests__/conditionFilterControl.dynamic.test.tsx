import React, { useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ConditionFilterControl from '@/app/ops-analysis/components/conditionFilterControl';

const api = vi.hoisted(() => ({
  getDataSourceList: vi.fn(async () => [
    { id: 3, rest_api: 'cmdb/list_cmdb_attr_options', name: '属性' },
  ]),
  getSourceDataByApiId: vi.fn(),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceList: api.getDataSourceList,
    getSourceDataByApiId: api.getSourceDataByApiId,
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

afterEach(() => {
  cleanup();
  api.getSourceDataByApiId.mockReset();
});

describe('dynamic condition fields', () => {
  it('loads fields from the configured source and only opens a select when options come back', async () => {
    api.getSourceDataByApiId.mockResolvedValue({
      data: [
        {
          attr_id: 'status',
          attr_name: '状态',
          value_type: 'enum',
          options: [{ value: '1', label: '已上线' }],
        },
        { attr_id: 'name', attr_name: '名称', value_type: 'string', options: [] },
      ],
    });
    const Harness = () => {
      const [value, setValue] = useState<unknown>({ logic: 'AND', items: [] });
      return (
        <ConditionFilterControl
          source={{
            kind: 'dynamic',
            sourceRef: { type: 'rest_api', value: 'cmdb/list_cmdb_attr_options' },
            valueField: 'attr_id',
            labelField: 'attr_name',
            queryParams: { model_id: { ref: 'model_id' } },
          }}
          formParams={{ model_id: 'host' }}
          value={value}
          onChange={setValue}
        />
      );
    };
    render(<Harness />);

    await waitFor(() => {
      expect(api.getSourceDataByApiId).toHaveBeenCalledWith(3, { model_id: 'host' });
    });
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.conditionFilter.add' }));
    const field = await screen.findByTestId('condition-field');
    fireEvent.mouseDown(field.querySelector('input') || field);
    expect(await screen.findByText('状态')).toBeTruthy();
    expect(screen.getByText('名称')).toBeTruthy();
    fireEvent.click(screen.getByText('状态'));
    const value = await screen.findByTestId('condition-value');
    expect(value.className).toContain('ant-select');
  });

  it('does not request fields while the referenced parameter is empty', async () => {
    render(
      <ConditionFilterControl
        source={{
          kind: 'dynamic',
          sourceRef: { type: 'rest_api', value: 'cmdb/list_cmdb_attr_options' },
          valueField: 'attr_id',
          labelField: 'attr_name',
          queryParams: { model_id: { ref: 'model_id' } },
        }}
        formParams={{ model_id: '' }}
        value={{ logic: 'AND', items: [{ field: 'status', op: 'eq', value: '1' }] }}
        onChange={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(api.getSourceDataByApiId).not.toHaveBeenCalled();
    });
  });

  it('renders a static source field as an input', async () => {
    render(
      <ConditionFilterControl
        source={{
          kind: 'static',
          items: [{ value: 'source', label: '来源', valueType: 'string' }],
        }}
        value={{ logic: 'AND', items: [{ field: 'source', op: 'eq', value: '' }] }}
      />,
    );
    expect(screen.getByLabelText('dashboard.conditionFilter.value').tagName).toBe('INPUT');
  });
});
