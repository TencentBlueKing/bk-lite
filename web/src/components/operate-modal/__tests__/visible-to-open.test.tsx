import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import OperateModal from '..';

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

const antdOutput = (spy: ReturnType<typeof vi.spyOn>) =>
  spy.mock.calls.map((args) => args.map(String).join(' ')).join('\n');

describe('OperateModal visible compatibility', () => {
  it('accepts visible without the deprecated Modal visible warning', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    render(
      <OperateModal footer={null} title="列设置" visible>
        <span>字段内容</span>
      </OperateModal>,
    );

    expect(screen.getByText('字段内容')).toBeTruthy();

    const logs = `${antdOutput(error)}\n${antdOutput(warn)}`;
    expect(logs).not.toMatch(/\[antd: Modal\].*visible.*is deprecated/);

    error.mockRestore();
    warn.mockRestore();
  });
});
