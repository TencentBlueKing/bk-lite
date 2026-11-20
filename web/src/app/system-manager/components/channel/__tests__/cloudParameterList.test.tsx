import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import CloudParameterList from '../cloudParameterList';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

beforeAll(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

afterEach(cleanup);

const row = { source: 'literal' as const, name: 'code', value: '1' };

describe('CloudParameterList', () => {
  it('shows the parameter name only when asked', () => {
    const { rerender } = render(<CloudParameterList value={[row]} showName />);
    expect(screen.getByPlaceholderText('system.channel.settings.cloudParameterName')).toBeTruthy();

    rerender(<CloudParameterList value={[row]} />);
    expect(screen.queryByPlaceholderText('system.channel.settings.cloudParameterName')).toBeNull();
  });

  it('declares cloud variables without a value source', () => {
    render(<CloudParameterList value={[{ ...row, test_value: '告警' }]} declareOnly showName />);
    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.getByPlaceholderText('system.channel.settings.cloudParameterName')).toBeTruthy();
    expect(screen.getByDisplayValue('告警')).toBeTruthy();
    expect(screen.queryByPlaceholderText('system.channel.settings.cloudLiteral')).toBeNull();
  });
});
