import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

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

const section = {
  id: 'section-1',
  valueConfig: {
    name: 'CMDB 模型实例明细',
    chartType: 'table',
  },
};

const sceneSection = {
  id: 'section-topo',
  valueConfig: {
    name: '网络状态拓扑',
    chartType: 'networkStatusTopology',
    sceneWidgetType: 'networkStatusTopology',
  },
};

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
});

describe('ReportWidgetCard copy menu', () => {
  it('includes 复制 for a data widget in edit mode', async () => {
    const user = userEvent.setup();
    render(
      <ReportWidgetCard
        section={section as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.copy')).toBeTruthy();
  });

  it('omits 复制 in view mode', () => {
    render(
      <ReportWidgetCard
        section={section as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'common.more' })).toBeNull();
    expect(screen.queryByText('common.copy')).toBeNull();
  });

  it('omits 复制 entirely for a networkStatusTopology scene widget', async () => {
    const user = userEvent.setup();
    render(
      <ReportWidgetCard
        section={sceneSection as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('common.delete')).toBeTruthy();
  });

  it('omits 复制 in share mode', async () => {
    const user = userEvent.setup();
    render(
      <ReportWidgetCard
        section={section as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing
        shareMode
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('common.delete')).toBeTruthy();
  });

  it('omits 复制 on a builtin report', async () => {
    const user = userEvent.setup();
    render(
      <ReportWidgetCard
        section={section as never}
        index={0}
        unifiedFilterValues={{}}
        filterDefinitions={[]}
        filterSearchVersion={0}
        editing
        isBuiltIn
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'common.more' }));
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('common.delete')).toBeTruthy();
  });
});
