import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { ParamInputControl } from '@/app/ops-analysis/components/paramInputControl';
import type { InputControlConfig } from '@/app/ops-analysis/types/dataSource';

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceList: vi.fn(async () => []),
    getSourceDataByApiId: vi.fn(),
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
});

const radioConfig: InputControlConfig = {
  control: 'radio',
  optionsSource: {
    type: 'static',
    staticItems: [
      { label: '主机 A', value: 'a' },
      { label: '主机 B', value: 'b' },
      { label: '主机 C', value: 'c' },
    ],
  },
};

describe('radio default value picker', () => {
  it('picks one stored value from a searchable select', () => {
    const onChange = vi.fn();
    const view = render(
      <ParamInputControl
        valuePicker
        inputConfig={radioConfig}
        fallback={<span>fallback</span>}
        value="b"
        onChange={onChange}
      />,
    );

    expect(screen.queryByRole('radio')).toBeNull();
    expect(screen.getByText('主机 B')).toBeTruthy();

    fireEvent.mouseDown(screen.getByRole('combobox'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '主机 C' } });
    expect(screen.queryByText('主机 A')).toBeNull();
    fireEvent.click(screen.getByText('主机 C'));
    expect(onChange).toHaveBeenCalledWith('c');

    const clear = view.container.querySelector('.ant-select-clear');
    expect(clear).toBeTruthy();
    fireEvent.mouseDown(clear as Element);
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('keeps runtime radios when a value picker is not requested', () => {
    render(
      <ParamInputControl
        inputConfig={radioConfig}
        fallback={<span>fallback</span>}
        value="a"
      />,
    );

    expect(screen.getAllByRole('radio')).toHaveLength(3);
    expect(screen.queryByRole('combobox')).toBeNull();
  });
});
