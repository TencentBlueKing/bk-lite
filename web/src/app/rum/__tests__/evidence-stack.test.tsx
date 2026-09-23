import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback || _key }),
}));

vi.mock('antd', () => ({
  Button: ({
    onClick,
    'aria-label': ariaLabel,
  }: {
    onClick?: () => void;
    'aria-label'?: string;
  }) => (
    <button type="button" aria-label={ariaLabel} onClick={onClick}>
      {ariaLabel}
    </button>
  ),
}));

vi.mock('@ant-design/icons', () => ({
  CopyOutlined: () => null,
  DownOutlined: () => null,
  UpOutlined: () => null,
}));

import EvidenceStack from '@/app/rum/errors/ui/evidence-stack';

afterEach(() => {
  cleanup();
});

describe('EvidenceStack', () => {
  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('shows empty copy for blank or invalid raw stacks', () => {
    const { unmount } = render(<EvidenceStack raw="" />);
    expect(screen.getByText('没有可用栈帧')).toBeTruthy();
    unmount();
    const second = render(<EvidenceStack raw="{not-json" />);
    expect(screen.getByText('没有可用栈帧')).toBeTruthy();
    second.unmount();
    render(<EvidenceStack raw='{"oops":true}' />);
    expect(screen.getByText('没有可用栈帧')).toBeTruthy();
  });

  it('renders app frames and hides library frames until expanded', () => {
    const raw = JSON.stringify([
      { functionName: 'handleClick', file: '/src/app.ts', line: 10, column: 2, resolved: true },
      { function: 'vendorBoot', filename: '/node_modules/react-dom/index.js', line: 1, column: 1 },
    ]);
    render(<EvidenceStack raw={raw} />);
    expect(screen.getByText('handleClick')).toBeTruthy();
    expect(screen.getByText('已还原')).toBeTruthy();
    expect(screen.queryByText('vendorBoot')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /库栈帧/ }));
    expect(screen.getByText('vendorBoot')).toBeTruthy();
  });

  it('copies a frame summary to the clipboard', () => {
    const raw = JSON.stringify([
      { functionName: 'boom', file: '/src/x.ts', line: 3, column: 4 },
    ]);
    render(<EvidenceStack raw={raw} />);
    fireEvent.click(screen.getAllByLabelText('复制')[0]);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('boom (/src/x.ts:3:4)');
  });
});
