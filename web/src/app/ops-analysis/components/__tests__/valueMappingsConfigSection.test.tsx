import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { ValueMappingsConfigSection } from '../valueMappingsConfigSection';
import type { ValueMapping } from '@/app/ops-analysis/utils/valueMapping';

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

const Harness = () => {
  const [mappings, setMappings] = useState<ValueMapping[]>([]);
  return (
    <>
      <ValueMappingsConfigSection
        t={(key) => key}
        value={mappings}
        onChange={setMappings}
      />
      <pre data-testid="mappings-dump">{JSON.stringify(mappings)}</pre>
    </>
  );
};

const readDump = (): ValueMapping[] =>
  JSON.parse(screen.getByTestId('mappings-dump').textContent || '[]');

describe('ValueMappingsConfigSection', () => {
  it('adds a rule with empty result and an unselected color picker', () => {
    render(<Harness />);

    fireEvent.click(screen.getByText('topology.nodeConfig.valueMappingsAdd'));

    expect(readDump()).toEqual([
      {
        type: 'value',
        value: '',
        result: {},
      },
    ]);
    expect(document.querySelector('.ant-color-picker-clear')).not.toBeNull();
    expect(document.querySelector('.ant-color-picker-color-block')).toBeNull();
  });

  it('persists mapped text without inventing a color, and omits blank text', () => {
    render(<Harness />);

    fireEvent.click(screen.getByText('topology.nodeConfig.valueMappingsAdd'));
    fireEvent.change(
      screen.getByPlaceholderText('topology.nodeConfig.valueMappingsResultText'),
      { target: { value: '离线' } },
    );

    expect(readDump()).toEqual([
      {
        type: 'value',
        value: '',
        result: { text: '离线' },
      },
    ]);

    fireEvent.change(
      screen.getByPlaceholderText('topology.nodeConfig.valueMappingsResultText'),
      { target: { value: '   ' } },
    );

    expect(readDump()).toEqual([
      {
        type: 'value',
        value: '',
        result: {},
      },
    ]);
  });
});
