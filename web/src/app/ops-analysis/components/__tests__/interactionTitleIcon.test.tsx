import React from 'react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import InteractionTitleIcon from '@/app/ops-analysis/components/interactionTitleIcon';
import { ShareModeProvider } from '@/app/ops-analysis/context/shareMode';
import { InteractionSurfaceProvider } from '@/app/ops-analysis/context/interactionSurface';
import ScreenWidgetFrame from '@/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame';
import type { WidgetInteractionLink } from '@/app/ops-analysis/types/dashBoard';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';

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

const titleLink: WidgetInteractionLink = {
  kind: 'title',
  name: '查看详情',
  url: '/ops',
  openMode: 'sameTab',
};

const widget = (
  interaction?: WidgetInteractionLink,
  frame?: 'panel' | 'bare',
): ScreenWidgetItem => ({
  id: 'w1',
  type: 'widget',
  chartType: 'line',
  title: 'CPU 使用率',
  x: 0,
  y: 0,
  w: 240,
  h: 160,
  zIndex: 1,
  valueConfig: {
    chartType: 'line',
    ...(frame ? { appearance: { frame } } : {}),
    ...(interaction ? { interaction } : {}),
  },
});

const renderWithIntl = (node: React.ReactNode) => render(
  <IntlProvider locale="zh" messages={{}}>
    {node}
  </IntlProvider>,
);

describe('InteractionTitleIcon', () => {
  it('renders an export icon and keeps the floating placement until hover', () => {
    renderWithIntl(
      <InteractionTitleIcon config={{ interaction: titleLink }} floating />,
    );

    const button = screen.getByRole('button', { name: '查看详情' });
    expect(button.querySelector('.anticon-export')).toBeTruthy();
    expect(button.querySelector('.anticon-link')).toBeNull();
    expect(button.querySelector('.anticon-share-alt')).toBeNull();
    expect(button.className).toContain('opacity-0');
    expect(button.className).toContain('group-hover:opacity-100');
    expect(button.className).toContain('group-focus-within:opacity-100');
    expect(button.className).toContain('text-(--color-text-3)');
    expect(button.className).toContain('absolute');
    expect(button.className).toContain('right-2');
    expect(button.className).toContain('top-2');
    expect(button.className).toContain('rounded-full');
    expect(button.className).toContain('h-6');
    expect(button.className).toContain('no-drag');
    expect(button.className).not.toContain('screen-widget-frame__title-link');
    expect(button.getAttribute('aria-label')).toBe('查看详情');
    expect(button.getAttribute('data-export-hidden')).toBe('true');
  });

  it('悬停显示链接名称，名称为空时回落到打开链接', async () => {
    const { rerender } = renderWithIntl(
      <InteractionTitleIcon config={{ interaction: titleLink }} />,
    );

    fireEvent.mouseEnter(screen.getByRole('button', { name: '查看详情' }));
    expect(await screen.findByRole('tooltip')).toHaveProperty('textContent', '查看详情');

    rerender(
      <IntlProvider locale="zh" messages={{}}>
        <InteractionTitleIcon config={{ interaction: { ...titleLink, name: '  ' } }} />
      </IntlProvider>,
    );
    const fallback = screen.getByRole('button', { name: '打开链接' });
    fireEvent.mouseEnter(fallback);
    expect((await screen.findAllByRole('tooltip')).some((node) => node.textContent === '打开链接')).toBe(true);
  });

  it('编辑态悬停提示查看模式下可跳转', async () => {
    renderWithIntl(
      <InteractionSurfaceProvider editing>
        <InteractionTitleIcon config={{ interaction: titleLink }} />
      </InteractionSurfaceProvider>,
    );
    fireEvent.mouseEnter(screen.getByRole('button', { name: '查看详情' }));
    expect(await screen.findByText('查看模式下可跳转')).toBeTruthy();
  });

  it('hides the entry on the share surface and for data links', () => {
    const { rerender } = render(
      <IntlProvider locale="zh" messages={{}}>
        <ShareModeProvider value>
          <InteractionTitleIcon config={{ interaction: titleLink }} variant="screen" />
        </ShareModeProvider>
      </IntlProvider>,
    );
    expect(screen.queryByRole('button')).toBeNull();

    rerender(
      <IntlProvider locale="zh" messages={{}}>
        <InteractionTitleIcon
          config={{
            chartType: 'line',
            interaction: { ...titleLink, kind: 'data' },
          }}
          variant="screen"
        />
      </IntlProvider>,
    );
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('screen title link', () => {
  it('places a scaled chevron at the far right of the framed title and leaves an unlinked title unchanged', () => {
    const { rerender } = renderWithIntl(
      <ScreenWidgetFrame item={widget(titleLink)}>
        <div>chart</div>
      </ScreenWidgetFrame>,
    );

    const button = screen.getByRole('button', { name: '查看详情' });
    const title = screen.getByText('CPU 使用率');
    expect(button.className).toContain('screen-widget-frame__title-link');
    expect(button.className).not.toContain('text-(--color-text-2)');
    expect(button.querySelector('.anticon-export')).toBeTruthy();
    expect(button.querySelector('.anticon-link')).toBeNull();
    expect(button.querySelector('.anticon-share-alt')).toBeNull();
    expect(button.getAttribute('data-export-hidden')).toBe('true');
    expect(button.parentElement?.className).toContain('screen-widget-frame__title-row');
    expect(button.parentElement?.lastElementChild).toBe(button);
    expect(title.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(title.closest('button')).toBeNull();
    expect(button.parentElement?.parentElement?.className).toContain('screen-widget-frame__header');
    expect(title.className).toBe('screen-widget-frame__title');

    rerender(
      <IntlProvider locale="zh" messages={{}}>
        <ScreenWidgetFrame item={widget()}>
          <div>chart</div>
        </ScreenWidgetFrame>
      </IntlProvider>,
    );
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('CPU 使用率').className).toBe('screen-widget-frame__title');
  });

  it('无边框大屏不渲染标题链接，数据链接配置也不画出标题图标', () => {
    const { rerender } = renderWithIntl(
      <ScreenWidgetFrame item={widget(titleLink, 'bare')}>
        <div>chart</div>
      </ScreenWidgetFrame>,
    );

    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByText('CPU 使用率')).toBeNull();
    expect(screen.getByText('chart')).toBeTruthy();

    rerender(
      <IntlProvider locale="zh" messages={{}}>
        <ScreenWidgetFrame
          item={widget({ ...titleLink, kind: 'data' }, 'bare')}
        >
          <div>chart</div>
        </ScreenWidgetFrame>
      </IntlProvider>,
    );
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('screen title link styles', () => {
  it('keeps the full-width title unless a link is present, then follows the screen chrome scale', () => {
    const source = readFileSync(
      path.join(process.cwd(), 'src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx'),
      'utf8',
    );
    expect(source).toContain(`width: 100%;
          overflow: hidden;`);
    expect(source).toContain(`.screen-widget-frame__title-row {
          display: flex;
          align-items: center;
          gap: calc(6px * var(--screen-widget-ui-scale));`);
    expect(source).toContain(`width: auto;
          flex: 1 1 auto;`);
    expect(source).toContain(`.screen-widget-frame__title-link {
          display: inline-flex;
          flex-shrink: 0;
          align-items: center;
          justify-content: center;
          margin-left: calc(-6px * var(--screen-widget-ui-scale));
          width: 0;`);
    expect(source).toContain(`.screen-widget-frame--editable:hover .screen-widget-frame__header:has(.screen-widget-frame__title-link),
        .screen-widget-frame--editable:focus-within .screen-widget-frame__header:has(.screen-widget-frame__title-link) {
          padding-right: calc((var(--screen-widget-title-padding, 10px) + 8px) * var(--screen-widget-ui-scale));`);
    expect(source).toContain('font-size: calc(14px * var(--screen-widget-ui-scale));');
    expect(source).toContain(
      'color-mix(in srgb, var(--screen-chrome-accent) 68%, var(--screen-widget-title-color))',
    );
    expect(source).not.toContain('screen-widget-frame__title-link--floating');
    expect(source).not.toContain('#02060c');
    expect(source).not.toContain('rgba(4, 12, 22');
    expect(source).toContain('opacity: 0;\n          pointer-events: none;');
    expect(source).toContain(`.screen-rnd-node:hover .screen-widget-frame__title-link,
        .screen-rnd-node:focus-within .screen-widget-frame__title-link,
        .screen-widget-frame:hover .screen-widget-frame__title-link,
        .screen-widget-frame:focus-within .screen-widget-frame__title-link {
          width: calc(14px * var(--screen-widget-ui-scale));
          margin-left: auto;
          overflow: visible;
          opacity: 1;
          pointer-events: auto;`);
    expect(source).toContain('drop-shadow(0 0 calc(6px * var(--screen-widget-ui-scale)) var(--screen-chrome-glow))');
    expect(source).toContain('text-overflow: ellipsis;');
    expect(source).not.toContain('screen-widget-frame__title-link-name');
    expect(source).not.toContain('--color-text-2');
  });
});
