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

    expect(screen.getAllByRole('combobox')).toHaveLength(2);
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
    expect(screen.getAllByRole('combobox')).toHaveLength(2);
  });

  it('计数函数仍然渲染字段选择', () => {
    render(
      <ConditionFilter
        data={[{ func: 'count', field: null, op: null, value: '' }]}
        fields={['service']}
        onChange={vi.fn()}
      />
    );

    expect(screen.getAllByRole('combobox')).toHaveLength(3);
  });
});
