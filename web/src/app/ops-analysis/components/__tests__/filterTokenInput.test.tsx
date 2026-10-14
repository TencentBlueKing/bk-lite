import React, { useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfigProvider } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { FilterTokenInput } from '@/app/ops-analysis/components/filterTokenInput';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(cleanup);

const biz: UnifiedFilterDefinition = {
  id: 'biz__string',
  key: 'biz',
  name: '业务',
  type: 'string',
  order: 1,
  enabled: true,
};

const disabledBiz: UnifiedFilterDefinition = {
  ...biz,
  id: 'biz__number',
  type: 'number',
  name: '业务数',
  enabled: false,
  order: 2,
};

const translate = (
  key: string,
  fallback?: string,
  values?: Record<string, string | number>,
) => {
  if (key === 'dashboard.filterTokenOption' && values) {
    return `${values.name}（${values.token} · ${values.type}）`;
  }
  if (key === 'dashboard.filterTokenTypeString') return '文本';
  if (key === 'dashboard.filterTokenHint') return '输入 $ 插入筛选';
  if (key === 'dashboard.filterTokenSeparator') return '、';
  if (key === 'dashboard.filterTokenUnmatched' && values) {
    return `${values.tokens} 未匹配到筛选项`;
  }
  return fallback ?? key;
};

const Harness = () => {
  const [value, setValue] = useState('');
  return (
    <FilterTokenInput
      t={translate}
      value={value}
      onChange={setValue}
      definitions={[biz, disabledBiz]}
    />
  );
};

describe('FilterTokenInput', () => {
  it('输入 $ 后插入启用筛选的变量，提示只在聚焦时挂在输入框下方', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const hint = screen.getByText('输入 $ 插入筛选');
    expect(hint.className).toContain('hidden');
    expect(hint.className).toContain('group-focus-within:block');
    expect(hint.parentElement?.className).toContain('flex-col');
    await user.type(screen.getByRole('textbox'), '$');

    const option = await screen.findByRole('option', { name: '业务（$biz$ · 文本）' });
    expect(screen.queryByRole('option', { name: /业务数/ })).toBeNull();
    await user.click(option);

    expect(screen.getByRole('textbox')).toHaveProperty('value', '$biz$');
  });

  it('没有启用筛选时不提示，输入 $ 也不打开菜单', async () => {
    const user = userEvent.setup();
    render(
      <FilterTokenInput
        t={translate}
        value=""
        definitions={[disabledBiz]}
      />,
    );

    expect(screen.queryByText('输入 $ 插入筛选')).toBeNull();
    await user.type(screen.getByRole('textbox'), '$');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('把匹配不到的变量合并显示在输入框下方', () => {
    render(
      <FilterTokenInput
        t={translate}
        value="$gone$ $biz$ $gone$ $room:number$"
        definitions={[biz, disabledBiz]}
      />,
    );

    expect(screen.getByRole('status').textContent).toBe('$gone$、$room:number$ 未匹配到筛选项');
  });

  it('补上变量结尾的 $ 只关闭菜单，不再当作新的 $', async () => {
    const user = userEvent.setup();
    render(
      <ConfigProvider theme={{ token: { motion: false } }}>
        <Harness />
      </ConfigProvider>,
    );
    const input = screen.getByRole('textbox');

    await user.type(input, '$biz$');

    expect(input).toHaveProperty('value', '$biz$');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('菜单关掉之后，变量结尾的 $ 不再打开新菜单', async () => {
    const user = userEvent.setup();
    render(
      <ConfigProvider theme={{ token: { motion: false } }}>
        <Harness />
      </ConfigProvider>,
    );
    const input = screen.getByRole('textbox');

    await user.type(input, '$biz');
    expect(await screen.findByRole('listbox')).toBeTruthy();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).toBeNull();

    await user.type(input, '$');

    expect(input).toHaveProperty('value', '$biz$');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('组字过程中的回车留给输入法，不插入高亮变量', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole('textbox');

    await user.type(input, '$');
    expect(await screen.findByRole('listbox')).toBeTruthy();

    fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
    expect(input).toHaveProperty('value', '$');
    expect(screen.getByRole('listbox')).toBeTruthy();

    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 });
    expect(input).toHaveProperty('value', '$');

    fireEvent.keyDown(input, { key: 'ArrowDown', keyCode: 229 });
    expect(screen.getByRole('option', { name: '业务（$biz$ · 文本）' }).getAttribute('aria-selected')).toBe('true');
  });
});
