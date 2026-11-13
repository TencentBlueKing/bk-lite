import React, { useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ConditionFilterInput from '@/app/ops-analysis/components/conditionFilterInput';
import OrderInput from '@/app/ops-analysis/components/orderInput';
import type { ConditionFieldOption } from '@/app/ops-analysis/types/dataSource';
import {
  parseConditionGroup,
  removeConditionRow,
  toggleConditionLogic,
} from '@/app/ops-analysis/utils/conditionFilter';
import { processDataSourceFormParamsForSubmit } from '@/app/ops-analysis/utils/dataSourceFormParams';
import { processDataSourceParams } from '@/app/ops-analysis/utils/widgetDataTransform';
import { parseOrderValue, serializeOrderValue } from '@/app/ops-analysis/utils/orderValue';

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
    t: (key: string) => key,
  }),
}));

afterEach(cleanup);

const fields: ConditionFieldOption[] = [
  { value: 'name', label: '名称', valueType: 'string' },
  { value: 'cpu', label: '核数', valueType: 'number' },
  { value: 'os', label: '系统', valueType: 'enum', options: [{ label: 'Linux', value: 'linux' }] },
];

const saved = {
  logic: 'OR' as const,
  items: [
    { field: 'name', op: 'eq', value: 'web' },
    { field: 'cpu', op: 'gt', value: 4 },
    { field: 'os', op: 'eq', value: 'linux' },
  ],
};

const Harness = ({ initial }: { initial: unknown }) => {
  const [value, setValue] = useState(initial);
  return (
    <>
      <ConditionFilterInput value={value} onChange={setValue} fields={fields} />
      <pre data-testid="stored">{JSON.stringify(value)}</pre>
    </>
  );
};

const stored = () => JSON.parse(screen.getByTestId('stored').textContent || '{}');

describe('condition filter rows can be deleted', () => {
  it('deletes a middle row and keeps the group logic and the other rows', () => {
    render(<Harness initial={saved} />);
    const buttons = screen.getAllByRole('button', { name: 'dashboard.conditionFilter.delete' });
    fireEvent.click(buttons[1]);
    const next = stored();
    expect(next.logic).toBe('OR');
    expect(next.items).toEqual([
      { field: 'name', op: 'eq', value: 'web' },
      { field: 'os', op: 'eq', value: 'linux' },
    ]);
  });

  it('submits an empty condition group after the last row is deleted', () => {
    render(<Harness initial={saved} />);
    while (screen.queryAllByRole('button', { name: 'dashboard.conditionFilter.delete' }).length > 0) {
      fireEvent.click(screen.getAllByRole('button', { name: 'dashboard.conditionFilter.delete' })[0]);
    }
    expect(stored()).toEqual({ logic: 'OR', items: [] });
    const submitted = processDataSourceFormParamsForSubmit(
      { filters: stored() },
      [{
        name: 'filters',
        alias_name: '条件过滤',
        type: 'conditionFilter',
        filterType: 'params',
        value: null,
      }],
    );
    expect(submitted[0].value).toEqual({ logic: 'OR', items: [] });
    const request = processDataSourceParams({
      sourceParams: submitted,
      chartType: 'table',
    });
    expect(request.filters).toEqual({ logic: 'OR', items: [] });
  });

  it('deletes rows that were restored from a saved condition group', () => {
    const restored = parseConditionGroup(JSON.parse(JSON.stringify(saved)));
    const withoutMiddle = removeConditionRow(restored, 1);
    expect(withoutMiddle.logic).toBe('OR');
    expect(withoutMiddle.items.map((item) => item.field)).toEqual(['name', 'os']);
    expect(toggleConditionLogic(withoutMiddle).logic).toBe('AND');
    render(<Harness initial={restored} />);
    fireEvent.click(screen.getAllByRole('button', { name: 'dashboard.conditionFilter.delete' })[0]);
    expect(stored().items.map((item: { field: string }) => item.field)).toEqual(['cpu', 'os']);
  });
});

describe('order value', () => {
  it('serializes the field and direction and echoes an old plain value', () => {
    expect(serializeOrderValue('created_at', true)).toBe('-created_at');
    expect(serializeOrderValue('name', false)).toBe('name');
    expect(parseOrderValue('-inst_name')).toEqual({ field: 'inst_name', descending: true });
    expect(parseOrderValue('legacy_field')).toEqual({ field: 'legacy_field', descending: false });
  });
});

const instanceCountFields: ConditionFieldOption[] = [
  { value: 'instance_count', label: '实例数', valueType: 'number' },
];

const openSelect = (select: HTMLElement) => {
  const selector = select.querySelector('.ant-select-selector');
  fireEvent.mouseDown(selector || select);
};

const hasClass = (node: Element | null | undefined, name: string) =>
  Boolean(node?.classList.contains(name));

const FormValue = ({ name }: { name: string }) => {
  const form = Form.useFormInstance();
  const value = Form.useWatch(name, form);
  return <pre data-testid="form-value">{JSON.stringify(value)}</pre>;
};

describe('condition rows keep field, operator and value inside a form', () => {
  it('shows a fixed instance-count field, operator and value, with one group logic control', () => {
    render(
      <Form>
        <Form.Item name="result_filter" initialValue={{ logic: 'AND', items: [] }}>
          <ConditionFilterInput fields={instanceCountFields} />
        </Form.Item>
        <FormValue name="result_filter" />
      </Form>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.conditionFilter.add' }));
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.conditionFilter.add' }));

    const rows = [0, 1].map((index) => screen.getByTestId(`condition-row-${index}`));
    rows.forEach((row) => {
      const field = within(row).getByTestId('condition-field');
      const operator = within(row).getByTestId('condition-operator');
      const value = within(row).getByTestId('condition-value');
      expect(field.closest('[data-slot="field"]')).toBeTruthy();
      expect(hasClass(operator.closest('[data-slot="operator"]'), 'shrink-0')).toBe(true);
      expect(value.closest('[data-slot="value"]')).toBeTruthy();
      expect(hasClass(field, 'ant-select-in-form-item')).toBe(true);
      expect(hasClass(operator, 'ant-select-in-form-item')).toBe(true);
      expect(hasClass(field, 'ant-select-disabled')).toBe(true);
      expect(within(row).getByText('实例数')).toBeTruthy();
      expect(within(row).getByText('dashboard.conditionFilter.gt')).toBeTruthy();
      expect(value.closest('.ant-input-number') || value).toBeTruthy();
      expect((value.closest('.ant-input-number') || value).className).toContain('ant-input-number');
    });
    expect(screen.getAllByTestId('condition-logic')).toHaveLength(1);
    expect(screen.getByText('dashboard.conditionFilter.matchAll')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'dashboard.conditionFilter.or' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'dashboard.conditionFilter.and' })).toBeNull();

    openSelect(screen.getByTestId('condition-logic'));
    fireEvent.click(screen.getByText('dashboard.conditionFilter.matchAny'));
    const last = JSON.parse(screen.getByTestId('form-value').textContent || '{}');
    expect(last.logic).toBe('OR');
    expect(last.items).toHaveLength(2);
    expect(last.items.every((item: { field: string }) => item.field === 'instance_count')).toBe(true);
  });

  it('echoes a saved enum value and can delete that row', () => {
    render(<Harness initial={saved} />);
    const enumRow = screen.getByTestId('condition-row-2');
    expect(within(enumRow).getByText('Linux')).toBeTruthy();
    expect(hasClass(within(enumRow).getByTestId('condition-value'), 'ant-select')).toBe(true);
    fireEvent.click(within(enumRow).getByRole('button', { name: 'dashboard.conditionFilter.delete' }));
    expect(stored().items.map((item: { field: string }) => item.field)).toEqual(['name', 'cpu']);
    expect(screen.queryByRole('button', { name: 'dashboard.conditionFilter.or' })).toBeNull();
  });
});

describe('order control', () => {
  it('shows the field and direction and echoes an old descending string', () => {
    render(
      <Form>
        <Form.Item name="order" initialValue="-instance_count">
          <OrderInput
            fields={[
              { value: 'instance_count', label: '实例数' },
              { value: 'model_name', label: '模型名称' },
            ]}
          />
        </Form.Item>
        <FormValue name="order" />
      </Form>,
    );
    const field = screen.getByTestId('order-field');
    const direction = screen.getByTestId('order-direction');
    expect(field.closest('[data-slot="order-field"]')).toBeTruthy();
    expect(hasClass(direction.closest('[data-slot="order-direction"]'), 'shrink-0')).toBe(true);
    expect(hasClass(field, 'ant-select-in-form-item')).toBe(true);
    expect(hasClass(direction, 'ant-select-disabled')).toBe(false);
    expect(screen.getByText('实例数')).toBeTruthy();
    expect(screen.getByText('dashboard.order.desc')).toBeTruthy();

    openSelect(direction);
    fireEvent.click(screen.getByText('dashboard.order.asc'));
    expect(screen.getByTestId('form-value').textContent).toBe('"instance_count"');
  });
});
