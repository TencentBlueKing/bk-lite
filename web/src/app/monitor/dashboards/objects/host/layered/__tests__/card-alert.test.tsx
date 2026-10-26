import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../layered.module.scss', () => ({
  default: new Proxy({}, { get: (_target, prop) => String(prop) })
}));

import { CardAlertDot } from '../card-alert';

describe('CardAlertDot', () => {
  it('主值色不再改折角，只有 fold=outline 描边', () => {
    const { container, rerender } = render(
      <CardAlertDot level="warn" valueColor="#FF7D00" />
    );
    const className = () => container.querySelector('[role="img"]')?.className ?? '';

    expect(className()).toContain('cardAlertFoldWarn');
    expect(className()).not.toContain('cardAlertFoldOutline');

    rerender(<CardAlertDot level="critical" valueColor="#F5222D" />);
    expect(className()).toContain('cardAlertFoldCritical');
    expect(className()).not.toContain('cardAlertFoldOutline');

    rerender(<CardAlertDot level="warn" fold="outline" valueColor="#FAAD14" />);
    expect(className()).toContain('cardAlertFoldOutline');

    rerender(<CardAlertDot level="none" fold="outline" />);
    expect(container.querySelector('[role="img"]')).toBeNull();
  });
});
