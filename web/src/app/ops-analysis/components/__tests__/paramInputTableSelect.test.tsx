import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ParamInputTableSelect from '../paramInputTableSelect';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, _default?: string, values?: Record<string, unknown>) => {
      if (key === 'paramInput.tableSelect.selected') {
        return `已选 ${values?.count ?? 0} 项`;
      }
      return key;
    },
  }),
}));

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

const options = [
  { label: '1111', value: '1111' },
  { label: '10.11.27.147[default] (10.11.27.147)', value: 'host-a' },
  { label: 'host-b', value: 'host-b' },
];

const Harness = ({
  onChange,
}: {
  onChange: (value: string | number | Array<string | number> | null) => void;
}) => {
  const [value, setValue] = useState<Array<string | number>>([]);
  return (
    <ParamInputTableSelect
      options={options}
      value={value}
      multiple
      placeholder="主机"
      onChange={(next) => {
        const nextValue = Array.isArray(next) ? next : [];
        setValue(nextValue);
        onChange(next);
      }}
    />
  );
};

describe('ParamInputTableSelect', () => {
  it('opens a table modal and commits checked rows on confirm', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    fireEvent.mouseDown(screen.getByRole('combobox'));

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('10.11.27.147[default] (10.11.27.147)')).toBeTruthy();

    const checkboxes = within(dialog).getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);
    fireEvent.click(checkboxes[3]);
    expect(within(dialog).getByText('已选 2 项')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.confirm' }));

    expect(onChange).toHaveBeenCalledWith(['1111', 'host-b']);
  });
});
