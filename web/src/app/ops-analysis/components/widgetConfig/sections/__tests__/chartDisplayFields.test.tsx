import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import React from 'react';
import zh from '@/app/ops-analysis/locales/zh.json';
import { ChartDisplayFields } from '../chartDisplayFields';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';

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

const Harness = ({
  chartType,
  surface,
  autoScroll = false,
}: {
  chartType: string;
  surface?: OpsAnalysisWidgetSurface;
  autoScroll?: boolean;
}) => {
  const [form] = Form.useForm();
  return (
    <Form form={form} initialValues={{ autoScroll, scrollSeconds: 2 }}>
      <ChartDisplayFields t={translate} chartType={chartType} surface={surface} />
    </Form>
  );
};

describe('chart display fields', () => {
  it('shows a count for ranking and does not show value sort', () => {
    render(<Harness chartType="topN" />);

    expect(screen.getByText('显示条数')).toBeTruthy();
    const count = screen.getByPlaceholderText('全部');
    expect(count.closest('.ant-form-item')?.className).toContain('col-span-2');
    expect(screen.queryByText('按数值排序')).toBeNull();
    expect(screen.queryByRole('switch')).toBeNull();
    expect(document.body.textContent?.includes('展示前几名')).toBe(false);
  });

  it('puts the count and value sort on one row for a bar', () => {
    render(<Harness chartType="bar" />);

    const count = screen.getByPlaceholderText('全部');
    expect(count.closest('.grid')?.className).toContain('grid-cols-4');
    expect(count.closest('.col-span-2')).toBeTruthy();
    expect(screen.getByRole('switch', { name: '按数值排序' }).closest('.col-span-1')).toBeTruthy();
    expect(screen.getByRole('switch', { name: '堆叠柱状' }).closest('.col-span-1')).toBeTruthy();
    expect(screen.getByRole('switch', { name: '按数值排序' })).toBeTruthy();
    expect(screen.getByRole('switch', { name: '堆叠柱状' })).toBeTruthy();
    expect(screen.getByRole('button', { name: /参考线/ })).toBeTruthy();
    expect(screen.queryByText('自动滚动')).toBeNull();
    expect(screen.getByLabelText('分类是时间时，条数和排序不生效。')).toBeTruthy();
    expect(screen.queryByText('分类是时间时，条数和排序不生效。')).toBeNull();
  });

  it('shows reference lines on a line and keeps zero and negatives available', () => {
    render(<Harness chartType="line" />);

    expect(screen.queryByPlaceholderText('全部')).toBeNull();
    expect(screen.queryByRole('switch')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /参考线/ }));
    const value = screen.getByRole('spinbutton', { name: '参考线数值' });
    expect(value.getAttribute('aria-valuemin')).toBeNull();
    expect(screen.getByRole('textbox', { name: '参考线名称' })).toBeTruthy();
    expect(screen.getByLabelText('参考线颜色')).toBeTruthy();
  });

  it('puts ranking count on its own row and splits scroll controls underneath', () => {
    const { unmount } = render(<Harness chartType="table" />);
    expect(screen.queryByText('自动滚动')).toBeNull();
    expect(screen.queryByText('每行秒数')).toBeNull();
    unmount();

    const { unmount: unmountOff } = render(<Harness chartType="topN" surface="screen" />);
    expect(screen.getByRole('switch', { name: /自动滚动/ })).toBeTruthy();
    expect(screen.queryByText('每行秒数')).toBeNull();
    fireEvent.click(screen.getByRole('switch', { name: /自动滚动/ }));
    expect(screen.getByRole('spinbutton', { name: '每行秒数' })).toBeTruthy();
    unmountOff();

    render(<Harness chartType="topN" surface="screen" autoScroll />);
    const count = screen.getByPlaceholderText('全部');
    const row = count.closest('.grid');
    expect(row?.className).toContain('grid-cols-2');
    expect(count.closest('.ant-form-item')?.className).toContain('col-span-2');
    const scrollSwitch = screen.getByRole('switch', { name: /自动滚动/ });
    expect(scrollSwitch.closest('.ant-form-item')?.className.includes('col-span-2')).toBe(false);
    expect(scrollSwitch.closest('.grid')).toBe(row);
    const seconds = screen.getByRole('spinbutton', { name: '每行秒数' });
    expect(seconds.closest('.ant-form-item')?.className.includes('col-span-2')).toBe(false);
    expect(seconds.closest('.grid')).toBe(row);
    expect((seconds as HTMLInputElement).value).toBe('2');
    expect(screen.getByLabelText('只滚动已经取到的行，不会自动翻页。鼠标放在组件上时暂停。')).toBeTruthy();
    expect(screen.queryByText('按数值排序')).toBeNull();
    cleanup();

    render(<Harness chartType="eventTable" surface="screen" autoScroll />);
    expect(screen.getByRole('spinbutton', { name: '每行秒数' })).toBeTruthy();
    cleanup();

    render(<Harness chartType="cardList" surface="screen" />);
    expect(screen.getByRole('switch', { name: /自动滚动/ })).toBeTruthy();
    expect(screen.queryByText('每行秒数')).toBeNull();
    cleanup();

    render(<Harness chartType="multiValue" surface="screen" autoScroll />);
    expect(screen.getByRole('spinbutton', { name: '每行秒数' })).toBeTruthy();
  });

  it('renders nothing for an event table off the screen', () => {
    const { container } = render(<Harness chartType="eventTable" />);
    expect(container.querySelector('.grid')).toBeNull();
  });
});
