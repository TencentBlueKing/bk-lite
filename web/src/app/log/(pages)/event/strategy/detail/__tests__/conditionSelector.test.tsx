import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import ConditionFilter from '../conditionSelector';

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

afterEach(() => {
  cleanup();
});

describe('条件函数选择', () => {
  it('选择速率后不渲染字段，阈值可以输入小数', () => {
    const onChange = vi.fn();
    render(
      <ConditionFilter
        data={[{ func: 'count_rate', field: '_msg', op: '>', value: '' }]}
        fields={['service', '_msg']}
        onChange={onChange}
      />
    );

    expect(screen.getAllByRole('combobox')).toHaveLength(3);
    expect(screen.queryByText('service')).toBeNull();
    expect(screen.getByText('log.event.countRateUnit')).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText('log.event.enterThreshold'), {
      target: { value: '0.5' },
    });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ func: 'count_rate', field: '_msg', value: '0.5' }),
    ]);
  });

  it('选择变化量后显示上一窗提示', () => {
    render(
      <ConditionFilter
        data={[{ func: 'count_delta', field: '_msg', op: '>', value: '50' }]}
        fields={['service']}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('log.event.countDeltaTip')).toBeTruthy();
    expect(screen.getAllByRole('combobox')).toHaveLength(3);
  });

  it('选择变化率后出现对照下拉和百分号', () => {
    render(
      <ConditionFilter
        data={[
          {
            func: 'count',
            field: '_msg',
            op: '>',
            value: '50',
            compare: { kind: 'percent', to: 'offset_24h' },
          },
        ]}
        fields={['service', '_msg']}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('log.event.compareKindPercent')).toBeTruthy();
    expect(screen.getByText('log.event.compareToOffset24h')).toBeTruthy();
    expect(screen.getByText('%')).toBeTruthy();
    expect(screen.getByText('log.event.percentTip')).toBeTruthy();
  });

  it('选择分位数后出现分位下拉，同时保留字段', () => {
    render(
      <ConditionFilter
        data={[
          {
            func: 'quantile',
            field: 'duration',
            op: '>',
            value: '2000',
            params: { quantile: 0.95 },
          },
        ]}
        fields={['duration']}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('P95')).toBeTruthy();
    expect(screen.getByText('duration')).toBeTruthy();
  });

  it('计数函数仍然渲染字段选择', () => {
    render(
      <ConditionFilter
        data={[{ func: 'count', field: null, op: null, value: '' }]}
        fields={['service']}
        onChange={vi.fn()}
      />
    );

    expect(screen.getAllByRole('combobox')).toHaveLength(4);
  });
});
