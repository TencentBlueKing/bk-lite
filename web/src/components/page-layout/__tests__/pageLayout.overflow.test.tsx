import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import PageLayout from '../index';

describe('PageLayout overflow', () => {
  it('lets the right pane shrink in a flex row and scroll wide content horizontally', () => {
    render(
      <PageLayout
        leftSection={<div>tree</div>}
        rightSection={<div data-testid="wide">table</div>}
      />,
    );

    const rightPane = screen.getByTestId('wide').parentElement;
    expect(rightPane?.className).toContain('min-w-0');
    expect(rightPane?.className).toContain('overflow-x-auto');
    expect(rightPane?.className).not.toContain('overflow-hidden');
  });
});
