import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ComCardList from '../comCardList';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

afterEach(cleanup);

const records = [{ title: 'Alpha' }, { title: 'Beta' }];
const titleConfig = {
  chartType: 'cardList',
  cardList: {
    titleField: 'title',
  },
};

describe('ComCardList layout branch', () => {
  it('enters the list layout branch by default', () => {
    render(<ComCardList rawData={records} config={titleConfig} />);

    expect(screen.getByText('Alpha')).toBeTruthy();
    expect(document.querySelector('[data-layout="list"]')).toBeTruthy();
    expect(document.querySelector('[data-layout="grid"]')).toBeNull();
  });

  it('enters the grid layout branch when layout is grid', () => {
    render(
      <ComCardList
        rawData={records}
        config={{
          ...titleConfig,
          cardList: {
            ...titleConfig.cardList,
            layout: 'grid',
          },
        }}
      />,
    );

    expect(screen.getByText('Beta')).toBeTruthy();
    expect(document.querySelector('[data-layout="grid"]')).toBeTruthy();
    expect(document.querySelector('[data-layout="list"]')).toBeNull();
  });

  it('vertically centers card rows and renders accent display modes', () => {
    const { container } = render(
      <ComCardList
        rawData={[
          { title: 'Alpha', severity: 'P1', seq: 'A1' },
          { title: 'Beta', severity: 'P2', seq: 'B1' },
        ]}
        config={{
          chartType: 'cardList',
          cardList: {
            titleField: 'title',
            leading: {
              type: 'field',
              field: 'seq',
              style: {
                displayType: 'colorBackground',
                valueMappings: [
                  {
                    type: 'value',
                    value: 'A1',
                    result: { text: 'A', color: '#00aa00' },
                  },
                ],
              },
            },
            badgeField: 'severity',
            badgeStyle: {
              valueMappings: [
                {
                  type: 'value',
                  value: 'P1',
                  result: { text: '紧急', color: '#ff0000' },
                },
              ],
            },
          },
        }}
      />,
    );

    const article = container.querySelector('article');
    expect(article?.className).toContain('items-center');
    expect(container.querySelector('[data-accent-mode="colorDot"]')).toBeTruthy();
    expect(container.querySelector('[data-accent-mode="text"]')).toBeTruthy();
    expect(screen.getByText('紧急')).toBeTruthy();
    expect(screen.getByText('P2')).toBeTruthy();
  });

  it('renders text with soft background accent', () => {
    const { container } = render(
      <ComCardList
        rawData={[{ title: 'Alpha', severity: 'warn' }]}
        config={{
          chartType: 'cardList',
          cardList: {
            titleField: 'title',
            badgeField: 'severity',
            badgeStyle: {
              displayType: 'textWithBackground',
              valueMappings: [
                {
                  type: 'value',
                  value: 'warn',
                  result: { text: '1项警告', color: '#f0a000' },
                },
              ],
            },
          },
        }}
      />,
    );

    const accent = container.querySelector(
      '[data-accent-mode="textWithBackground"]',
    ) as HTMLElement | null;
    expect(accent).toBeTruthy();
    expect(accent?.textContent).toBe('1项警告');
    expect(accent?.style.color).toBe('rgb(240, 160, 0)');
    expect(accent?.style.backgroundColor).toBe('rgba(240, 160, 0, 0.16)');
  });
});
