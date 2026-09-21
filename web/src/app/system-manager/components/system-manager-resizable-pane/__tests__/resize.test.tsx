import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import SystemManagerResizablePane from '@/app/system-manager/components/system-manager-resizable-pane';

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe('SystemManagerResizablePane', () => {
  it('keeps the pane between min and max while dragging', () => {
    render(
      <SystemManagerResizablePane
        storageKey="system-manager.test.sidebarWidth"
        defaultWidth={260}
        minWidth={200}
        maxWidth={420}
      >
        tree
      </SystemManagerResizablePane>,
    );

    const separator = screen.getByRole('separator');
    fireEvent.mouseDown(separator, { clientX: 260 });
    fireEvent.mouseMove(document, { clientX: 900 });
    expect(separator.getAttribute('aria-valuenow')).toBe('420');

    fireEvent.mouseMove(document, { clientX: 0 });
    expect(separator.getAttribute('aria-valuenow')).toBe('200');

    fireEvent.mouseUp(document);
    expect(localStorage.getItem('system-manager.test.sidebarWidth')).toBe('200');
  });
});
