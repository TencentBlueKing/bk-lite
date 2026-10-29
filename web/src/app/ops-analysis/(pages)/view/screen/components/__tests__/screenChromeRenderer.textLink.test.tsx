import React from 'react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { FilterTemplateProvider } from '@/app/ops-analysis/context/filterTemplate';
import { InteractionSurfaceProvider } from '@/app/ops-analysis/context/interactionSurface';
import { ShareModeProvider } from '@/app/ops-analysis/context/shareMode';
import type { ScreenTextItem } from '@/app/ops-analysis/types/screen';
import ScreenChromeRenderer from '../screenChromeRenderer';

const openNavigation = vi.hoisted(() => vi.fn());

vi.mock('@/app/ops-analysis/utils/interactionBehavior', async () => {
  const actual = await vi.importActual<typeof import('@/app/ops-analysis/utils/interactionBehavior')>(
    '@/app/ops-analysis/utils/interactionBehavior',
  );
  return { ...actual, openPreparedInteractionNavigation: openNavigation };
});

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

afterEach(() => {
  cleanup();
  openNavigation.mockClear();
});

const textItem = (
  overrides: Partial<ScreenTextItem> = {},
): ScreenTextItem => ({
  id: 'label-alert-source-event-top',
  kind: 'text',
  content: '告警关联事件来源 TOP10',
  x: 44,
  y: 1036,
  w: 240,
  h: 42,
  zIndex: 5,
  textStyle: { fontSize: 30, fontWeight: 600, color: 'canvas', align: 'left' },
  ...overrides,
});

const titleLink = {
  kind: 'title' as const,
  name: '查看告警',
  url: '/alerts?source=$source$',
  openMode: 'sameTab' as const,
};

const renderText = (item: ScreenTextItem, node?: React.ReactNode) => render(
  <IntlProvider locale="zh" messages={{}}>
    {node ?? <ScreenChromeRenderer item={item} />}
  </IntlProvider>,
);

describe('screen text title link', () => {
  it('leaves an unlinked text item unchanged', () => {
    const { container } = renderText(textItem());

    expect(screen.getByText('告警关联事件来源 TOP10')).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
    expect(container.querySelector('[data-screen-text-link]')).toBeNull();
    const text = container.querySelector('.screen-uniform-text') as HTMLElement;
    expect(text.getAttribute('data-align')).toBe('left');
    expect(text.style.fontSize).toBe('30px');
    expect(text.style.whiteSpace).toBe('pre-wrap');
  });

  it('pins the chevron to the far right and keeps the label alignment when the text is truncated', () => {
    const long = '告警关联事件来源 TOP10'.repeat(12);
    const { container, rerender } = renderText(textItem({
      content: long,
      interaction: titleLink,
    }));

    const button = screen.getByRole('button', { name: '查看告警' });
    const label = container.querySelector('[data-screen-text-label]') as HTMLElement;
    const row = container.querySelector('[data-screen-text-link]') as HTMLElement;
    expect(button.querySelector('.anticon-export')).toBeTruthy();
    expect(button.querySelector('.anticon-share-alt')).toBeNull();
    expect(button.className).toContain('screen-widget-frame__title-link');
    expect(button.className).toContain('screen-text-item__title-link');
    expect(button.getAttribute('title')).toBeNull();
    expect(button.getAttribute('data-export-hidden')).toBe('true');
    expect(label.textContent).toBe(long);
    expect(label.style.whiteSpace).toBe('nowrap');
    expect(label.style.textOverflow).toBe('ellipsis');
    expect(label.style.flex).toBe('1 1 auto');
    expect(label.className).toContain('min-w-0');
    expect(row.className).toContain('overflow-hidden');
    expect(row.className).toContain('justify-start');
    expect(row.style.fontSize).toBe('30px');
    expect(row.style.gap).toBe('0.4em');
    expect(row.lastElementChild).toBe(button);
    expect(label.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(label.contains(button)).toBe(false);

    rerender(
      <IntlProvider locale="zh" messages={{}}>
        <ScreenChromeRenderer item={textItem({
          content: '第一行\n第二行',
          textStyle: { fontSize: 20, align: 'center' },
          interaction: titleLink,
        })}
        />
      </IntlProvider>,
    );
    const centered = container.querySelector('[data-screen-text-link]') as HTMLElement;
    const wrapped = container.querySelector('[data-screen-text-label]') as HTMLElement;
    expect(centered.className).toContain('justify-start');
    expect(centered.getAttribute('data-align')).toBe('center');
    expect(wrapped.style.textAlign).toBe('center');
    expect(wrapped.style.flex).toBe('1 1 auto');
    expect(centered.lastElementChild).toBe(screen.getByRole('button', { name: '查看告警' }));
    expect(wrapped.style.whiteSpace).toBe('pre-wrap');
    expect(wrapped.style.textOverflow).toBe('clip');

    rerender(
      <IntlProvider locale="zh" messages={{}}>
        <ScreenChromeRenderer item={textItem({
          textStyle: { fontSize: 18, align: 'right' },
          interaction: titleLink,
        })}
        />
      </IntlProvider>,
    );
    const rightRow = container.querySelector('[data-screen-text-link]') as HTMLElement;
    expect(rightRow.className).toContain('justify-start');
    expect((rightRow.querySelector('[data-screen-text-label]') as HTMLElement).style.textAlign).toBe('right');
    expect(rightRow.lastElementChild).toBe(screen.getByRole('button', { name: '查看告警' }));
  });

  it('hides data links, empty urls, and the icon on the share surface', () => {
    const { rerender } = renderText(textItem({
      interaction: { ...titleLink, kind: 'data' },
    }));
    expect(screen.queryByRole('button')).toBeNull();

    rerender(
      <IntlProvider locale="zh" messages={{}}>
        <ScreenChromeRenderer item={textItem({
          interaction: { ...titleLink, url: '  ' },
        })}
        />
      </IntlProvider>,
    );
    expect(screen.queryByRole('button')).toBeNull();

    rerender(
      <IntlProvider locale="zh" messages={{}}>
        <ShareModeProvider value>
          <ScreenChromeRenderer item={textItem({ interaction: titleLink })} />
        </ShareModeProvider>
      </IntlProvider>,
    );
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('告警关联事件来源 TOP10')).toBeTruthy();
  });

  it('navigates only in view mode and still lets an edit-mode click select the text', async () => {
    const parentClick = vi.fn();
    const pointerDown = vi.fn();
    const { rerender } = render(
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
          appliedValues={{ source: 'network' }}
          resolveEnabled={false}
        >
          <div onClick={parentClick} onPointerDown={pointerDown}>
            <InteractionSurfaceProvider editing>
              <ScreenChromeRenderer item={textItem({ interaction: titleLink })} />
            </InteractionSurfaceProvider>
          </div>
        </FilterTemplateProvider>
      </IntlProvider>,
    );

    fireEvent.click(screen.getByText('告警关联事件来源 TOP10'));
    expect(openNavigation).not.toHaveBeenCalled();
    expect(parentClick).toHaveBeenCalled();
    parentClick.mockClear();

    const button = screen.getByRole('button', { name: '查看告警' });
    fireEvent.pointerDown(button);
    expect(pointerDown).toHaveBeenCalled();
    fireEvent.mouseEnter(button);
    expect(await screen.findByText('查看模式下可跳转')).toBeTruthy();
    fireEvent.click(button);
    expect(openNavigation).not.toHaveBeenCalled();
    expect(parentClick).toHaveBeenCalled();

    parentClick.mockClear();
    rerender(
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
          appliedValues={{ source: 'network' }}
          resolveEnabled={false}
        >
          <div onClick={parentClick}>
            <ScreenChromeRenderer item={textItem({ interaction: titleLink })} />
          </div>
        </FilterTemplateProvider>
      </IntlProvider>,
    );
    fireEvent.click(screen.getByText('告警关联事件来源 TOP10'));
    expect(openNavigation).not.toHaveBeenCalled();
    expect(parentClick).toHaveBeenCalled();
    parentClick.mockClear();
    fireEvent.click(screen.getByRole('button', { name: '查看告警' }));
    expect(parentClick).not.toHaveBeenCalled();
    expect(openNavigation).toHaveBeenCalledWith(
      expect.objectContaining({ href: '/alerts?source=network' }),
      window,
    );
  });

  it('sizes the text icon with the label and removes the focus ring', () => {
    const source = readFileSync(
      path.join(process.cwd(), 'src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx'),
      'utf8',
    );
    expect(source).toContain(`.screen-text-item__title-link {
          width: 0;
          margin-left: -0.4em;
          height: 1em;
          flex-shrink: 0;
          font-size: 1em;
          outline: none;`);
    expect(source).toContain(`.screen-widget-frame__title-link {
          display: inline-flex;
          flex-shrink: 0;
          align-items: center;
          justify-content: center;
          margin-left: calc(-6px * var(--screen-widget-ui-scale));
          width: 0;`);
    expect(source).toContain(`.screen-text-item__title-link:focus,
        .screen-text-item__title-link:focus-visible {
          outline: none;`);
    expect(source).toContain('.screen-widget-frame__title-link:hover {');
  });
});
