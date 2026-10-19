import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { FilterTemplateProvider } from '@/app/ops-analysis/context/filterTemplate';
import type { ScreenTextItem } from '@/app/ops-analysis/types/screen';
import { createScreenTextItem } from '../../utils/screenItems';
import ScreenTextLinkFields from '../screenTextLinkFields';

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

const renderFields = (item: ScreenTextItem, onChange: (item: ScreenTextItem) => void) => render(
  <IntlProvider locale="zh" messages={{}}>
    <FilterTemplateProvider
      definitions={[{
        id: 'source',
        key: 'source',
        name: '来源',
        type: 'string',
        order: 1,
        enabled: true,
      }]}
      appliedValues={{}}
      resolveEnabled={false}
    >
      <ScreenTextLinkFields item={item} onChange={onChange} />
    </FilterTemplateProvider>
  </IntlProvider>,
);

describe('ScreenTextLinkFields', () => {
  it('saves a title link with a canvas filter variable and clears it on none', async () => {
    const user = userEvent.setup();
    const item = createScreenTextItem([], { id: 'text-1', content: '说明' });
    const onChange = vi.fn();
    const view = renderFields(item, onChange);

    expect(screen.queryByRole('radio', { name: '数据链接' })).toBeNull();
    await user.click(screen.getByText('标题链接'));
    const url = await screen.findByPlaceholderText('输入 URL，键入 $ 插入变量');
    await user.type(url, '/alerts?source=');
    await user.type(url, '$');
    await user.click(await screen.findByRole('option', { name: /来源/ }));

    const saved = onChange.mock.calls.at(-1)?.[0] as ScreenTextItem;
    expect(saved.interaction).toEqual({
      kind: 'title',
      name: '',
      url: '/alerts?source=$source$',
      openMode: 'sameTab',
    });

    view.rerender(
      <IntlProvider locale="zh" messages={{}}>
        <FilterTemplateProvider
          definitions={[{
            id: 'source',
            key: 'source',
            name: '来源',
            type: 'string',
            order: 1,
            enabled: true,
          }]}
          appliedValues={{}}
          resolveEnabled={false}
        >
          <ScreenTextLinkFields item={saved} onChange={onChange} />
        </FilterTemplateProvider>
      </IntlProvider>,
    );
    await user.click(screen.getByText('无'));
    await waitFor(() => {
      const cleared = onChange.mock.calls.at(-1)?.[0] as ScreenTextItem;
      expect(cleared.interaction).toBeUndefined();
      expect(Object.prototype.hasOwnProperty.call(cleared, 'interaction')).toBe(false);
    });

    const cleared = onChange.mock.calls.at(-1)?.[0] as ScreenTextItem;
    view.rerender(
      <IntlProvider locale="zh" messages={{}}>
        <FilterTemplateProvider
          definitions={[]}
          appliedValues={{}}
          resolveEnabled={false}
        >
          <ScreenTextLinkFields item={cleared} onChange={onChange} />
        </FilterTemplateProvider>
      </IntlProvider>,
    );
    await user.click(screen.getByText('标题链接'));
    expect((await screen.findByPlaceholderText('输入 URL，键入 $ 插入变量') as HTMLInputElement).value).toBe('');
  });

  it('loads a stored title link', () => {
    const item = createScreenTextItem([], {
      id: 'text-1',
      content: '说明',
      interaction: {
        kind: 'title',
        name: '查看告警',
        url: '/alerts',
        openMode: 'newTab',
      },
    });
    renderFields(item, vi.fn());

    expect((screen.getByDisplayValue('查看告警') as HTMLInputElement).value).toBe('查看告警');
    expect((screen.getByDisplayValue('/alerts') as HTMLInputElement).value).toBe('/alerts');
    const newTab = screen.getByRole('radio', { name: '新标签' }) as HTMLInputElement;
    expect(newTab.checked || newTab.closest('.ant-segmented-item')?.className.includes('ant-segmented-item-selected')).toBe(true);
  });
});
