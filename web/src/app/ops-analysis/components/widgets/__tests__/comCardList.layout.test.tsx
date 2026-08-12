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
});
