import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ApmLayout from '../layout';

describe('ApmLayout', () => {
  it('inherits the application canvas without adding a module background', () => {
    const { container, getByText } = render(
      <ApmLayout>
        <div>APM content</div>
      </ApmLayout>,
    );

    const root = container.firstElementChild;

    expect(root?.getAttribute('class')).toBe('h-full min-h-full');
    expect(root?.getAttribute('style')).toBeNull();
    expect(getByText('APM content')).toBeTruthy();
  });
});
