import { cleanup, render, screen } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import React from 'react';
import zh from '@/app/ops-analysis/locales/zh.json';
import { ChartDisplayFields } from '../chartDisplayFields';

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

const dashboard = zh.dashboard;
const translate = (key: string) => {
  const id = key.startsWith('dashboard.') ? key.slice('dashboard.'.length) : key;
  const value = dashboard[id as keyof typeof dashboard];
  return typeof value === 'string' ? value : key;
};

const Harness = ({ chartType }: { chartType: string }) => {
  const [form] = Form.useForm();
  return (
    <Form form={form}>
      <ChartDisplayFields t={translate} chartType={chartType} />
    </Form>
  );
};

describe('chart display fields', () => {
  it('shows a count for ranking and does not show value sort', () => {
    render(<Harness chartType="topN" />);

    expect(screen.getByText('显示条数')).toBeTruthy();
    expect(screen.getByPlaceholderText('全部')).toBeTruthy();
    expect(screen.queryByText('按数值排序')).toBeNull();
    expect(screen.queryByRole('switch')).toBeNull();
    expect(document.body.textContent?.includes('展示前几名')).toBe(false);
  });

  it('puts the count and value sort on one row for a bar', () => {
    render(<Harness chartType="bar" />);

    const count = screen.getByPlaceholderText('全部');
    expect(count.closest('.grid')?.className).toContain('grid-cols-2');
    expect(screen.getByRole('switch', { name: '按数值排序' })).toBeTruthy();
    expect(screen.getByLabelText('分类是时间时，条数和排序不生效。')).toBeTruthy();
    expect(screen.queryByText('分类是时间时，条数和排序不生效。')).toBeNull();
  });
});
