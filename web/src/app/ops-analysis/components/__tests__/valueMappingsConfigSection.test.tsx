import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import {
  DEFAULT_VALUE_MAPPING_COLOR,
  ValueMappingsConfigSection,
} from '../valueMappingsConfigSection';
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

describe('ValueMappingsConfigSection', () => {
  it('persists the displayed default color when adding a rule', () => {
    render(<Harness />);

    fireEvent.click(screen.getByText('topology.nodeConfig.valueMappingsAdd'));

    const dumped = JSON.parse(
      screen.getByTestId('mappings-dump').textContent || '[]',
    );
    expect(dumped).toEqual([
      {
        type: 'value',
        value: '',
        result: { text: '', color: DEFAULT_VALUE_MAPPING_COLOR },
      },
    ]);
  });
});
