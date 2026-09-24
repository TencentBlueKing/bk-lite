import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import RumLayout from '../layout';

describe('RumLayout', () => {
  it('inherits the application canvas without extra module padding', () => {
    const { container, getByText } = render(
      <RumLayout>
        <div>RUM content</div>
      </RumLayout>,
    );

    const root = container.firstElementChild;
    const className = root?.getAttribute('class') || '';

    expect(className).toBe('flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden');
    expect(className).not.toMatch(/\bpx-4\b|\bpb-4\b|\b-mt-4\b/);
    expect(root?.getAttribute('style')).toBeNull();
    expect(getByText('RUM content')).toBeTruthy();
  });
});
