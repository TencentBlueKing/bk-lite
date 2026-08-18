import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ReportWidgetCard from '@/app/ops-analysis/components/reportWidgetCard';

vi.mock('@dnd-kit/sortable', () => ({
  useSortable: () => ({
    attributes: {},
    listeners: {},
    setNodeRef: vi.fn(),
    transform: null,
    transition: undefined,
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetDataRenderer', () => ({
  default: () => <div data-testid="widget-runtime" />,
}));

afterEach(() => {
  cleanup();
});

const section = {
  id: 'section-1',
  valueConfig: {
    name: 'CMDB 模型实例明细',
    chartType: 'table',
  },
};

describe('ReportWidgetCard print height', () => {
  it('does not mark the 420px card for print expand', () => {
    const { container } = render(
      <ReportWidgetCard
        section={section as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    const card = container.firstElementChild as HTMLElement | null;
    expect(card).not.toBeNull();
    expect(card?.getAttribute('data-export-expand')).toBeNull();
    expect(card?.style.height).toBe('420px');
    expect(container.querySelectorAll('[data-export-expand="true"]')).toHaveLength(0);
  });
});
