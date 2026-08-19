import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Password from '..';

const hint = '检测到密码首尾包含空格，已自动移除';

const renderPassword = (
  props: Partial<React.ComponentProps<typeof Password>> = {},
) => {
  const onChange = vi.fn();
  render(
    <IntlProvider
      locale="zh"
      messages={{ 'common.passwordWhitespaceTrimmed': hint }}
      onError={() => undefined}
    >
      <Password
        clickToEdit={false}
        placeholder="password-input"
        onChange={onChange}
        {...props}
      />
    </IntlProvider>,
  );
  return {
    input: screen.getByPlaceholderText('password-input') as HTMLInputElement,
    onChange,
  };
};

afterEach(() => {
  cleanup();
});

describe('Password 首尾空白处理', () => {
  it('粘贴后立即移除首尾空白并显示提示', async () => {
    const user = userEvent.setup();
    const { input, onChange } = renderPassword({ trimOuterWhitespace: true });

    await user.click(input);
    await user.paste('  pass word\n');

    expect(input.value).toBe('pass word');
    expect(onChange).toHaveBeenLastCalledWith('pass word');
    expect(screen.getByText(hint)).toBeTruthy();
  });

  it('普通输入在失焦时移除首尾空白', async () => {
    const user = userEvent.setup();
    const { input, onChange } = renderPassword({ trimOuterWhitespace: true });

    await user.type(input, '  pass word  ');
    expect(input.value).toBe('  pass word  ');

    await user.tab();

    expect(input.value).toBe('pass word');
    expect(onChange).toHaveBeenLastCalledWith('pass word');
    expect(screen.getByText(hint)).toBeTruthy();
  });

  it('默认不开启时保持其他业务模块原行为', async () => {
    const user = userEvent.setup();
    const { input } = renderPassword();

    await user.type(input, ' secret ');
    await user.tab();

    expect(input.value).toBe(' secret ');
    expect(screen.queryByText(hint)).toBeNull();
  });
});
