// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ComponentParamSwitchControl from '../componentParamSwitchControl';

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    Segmented: ({
      options,
      value,
    }: {
      options: Array<{ label: React.ReactNode; value: string | number }>;
      value?: string | number;
    }) => (
      <div data-testid="segmented" data-value={String(value)}>
        {options.map((option) => (
          <span key={String(option.value)}>{option.label}</span>
        ))}
      </div>
    ),
    Select: ({ value }: { value?: string | number }) => (
      <div data-testid="select" data-value={String(value)} />
    ),
  };
});

afterEach(cleanup);

describe('ComponentParamSwitchControl screen theme', () => {
  const options = [
    { label: 'A', value: 'a' },
    { label: 'B', value: 'b' },
  ];

  it('wraps screen-dark Segmented with provider and no color SCSS class', () => {
    const { container } = render(
      <ComponentParamSwitchControl
        inputConfig={{ control: 'radio', componentSwitch: true }}
        options={options}
        value="a"
        chartThemeMode="screen-dark"
      />,
    );

    expect(
      container.querySelector('[data-screen-widget-theme="screen-dark"]'),
    ).toBeTruthy();
    expect(screen.getByTestId('segmented')).toBeTruthy();
    expect(container.querySelector('[class*="screenControl"]')).toBeNull();
  });

  it('does not add screen wrapper for default theme', () => {
    const { container } = render(
      <ComponentParamSwitchControl
        inputConfig={{ control: 'select', componentSwitch: true }}
        options={options}
        value="a"
      />,
    );

    expect(container.querySelector('[data-screen-widget-theme]')).toBeNull();
    expect(screen.getByTestId('select')).toBeTruthy();
  });
});
