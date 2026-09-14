import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
});

const stubOverflow = (overflows: boolean) => {
  Object.defineProperty(HTMLElement.prototype, 'scrollWidth', {
    configurable: true,
    get() {
      return overflows ? 200 : 80;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() {
      return 80;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
    configurable: true,
    get() {
      return 20;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get() {
      return 20;
    },
  });
};

describe('EllipsisWithTooltip', () => {
  it('does not show a tooltip when the text fits', async () => {
    stubOverflow(false);
    const user = userEvent.setup();
    render(
      <EllipsisWithTooltip
        text={<span>短摘要</span>}
        tooltip="完整摘要不应出现"
        className="truncate"
      />,
    );

    await user.hover(screen.getByText('短摘要'));
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('shows the string tooltip instead of the rendered node when overflowing', async () => {
    stubOverflow(true);
    const user = userEvent.setup();
    render(
      <EllipsisWithTooltip
        text={<span>可见文本</span>}
        tooltip="完整摘要标题"
        className="truncate"
      />,
    );

    await user.hover(screen.getByText('可见文本'));
    expect((await screen.findByRole('tooltip')).textContent).toContain('完整摘要标题');
  });
});
