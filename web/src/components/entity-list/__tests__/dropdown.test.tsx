import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Menu } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import EntityList from '..';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/components/icon', () => ({
  default: ({ type }: { type: string }) => <span data-testid={`icon-${type}`} />,
}));

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

const antdOutput = (spy: ReturnType<typeof vi.spyOn>) =>
  spy.mock.calls.map((args) => args.map(String).join(' ')).join('\n');

describe('EntityList card actions dropdown', () => {
  it('opens menu actions without the deprecated overlay warning', async () => {
    const user = userEvent.setup();
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    render(
      <EntityList
        data={[
          {
            id: 'region-1',
            name: 'Default',
            description: 'cloud region',
            icon: 'yunquyu',
          },
        ]}
        loading={false}
        menuActions={() => (
          <Menu>
            <Menu.Item key="edit">编辑</Menu.Item>
          </Menu>
        )}
      />,
    );

    await user.click(screen.getByTestId('icon-sangedian-copy'));
    expect(await screen.findByText('编辑')).toBeTruthy();

    const logs = `${antdOutput(error)}\n${antdOutput(warn)}`;
    expect(logs).not.toMatch(/\[antd: Dropdown\].*overlay.*is deprecated/);

    error.mockRestore();
    warn.mockRestore();
  });
});
