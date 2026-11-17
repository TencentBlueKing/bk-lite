// @vitest-environment jsdom

import React, { useState } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import EventTable from '@/app/ops-analysis/components/widgets/eventTable/eventTable';
import ShowcaseEventTable from '@/app/ops-analysis/components/ops-analysis-widgets/event-table';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
  }),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get() {
      return 240;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() {
      return 526;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get() {
      const name = String((this as HTMLElement).className || '');
      if (name.includes('ant-pagination')) return 72;
      if (name.includes('ant-table-header') || name.includes('ant-table-thead')) return 39;
      return 0;
    },
  });
});

afterEach(() => {
  cleanup();
});

const rows = [
  { id: 'fixture-1', summary: 'FIXTURE-事件-1', metric: 'cpu' },
  { id: 'fixture-2', summary: 'FIXTURE-事件-2', metric: 'mem' },
];

const columns = [
  { key: 'summary', title: '摘要', visible: true, order: 0 },
  { key: 'metric', title: '监控项', visible: true, order: 1 },
];

const plainSource = { params: [{ name: 'limit' }] } as any;

const LateEvent = ({
  Table,
}: {
  Table: typeof EventTable;
}) => {
  const [visible, setVisible] = useState(false);
  return (
    <div style={{ width: 526, height: 268 }}>
      <button type="button" onClick={() => setVisible(true)}>补列</button>
      <button type="button" onClick={() => setVisible(false)}>卸列</button>
      <Table
        rawData={rows}
        loading={false}
        dataSource={plainSource}
        config={{
          chartType: 'eventTable',
          tableConfig: { columns: visible ? columns : [] },
        }}
      />
    </div>
  );
};

const expectMeasuredBody = (container: HTMLElement) => {
  const body = container.querySelector<HTMLElement>('.ant-table-body');
  expect(body).not.toBeNull();
  expect(body?.style.maxHeight || body?.style.height).toBe('201px');
};

describe('event table columns mount after the first paint', () => {
  it.each([
    ['运行时事件表', EventTable],
    ['展示副本事件表', ShowcaseEventTable],
  ] as const)('%s 在无列后再挂列、卸列再挂列后仍测量表体', async (label, Table) => {
    const view = render(<LateEvent Table={Table} />);
    expect(view.container.querySelector('.ant-table-body')).toBeNull();
    expect(view.container.querySelector('.ant-table-content')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '补列' }));
    expectMeasuredBody(view.container);

    await userEvent.click(screen.getByRole('button', { name: '卸列' }));
    expect(view.container.querySelector('.ant-table-body')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '补列' }));
    expectMeasuredBody(view.container);
    expect(label).toContain('事件表');
  });

  it.each([
    ['运行时事件表', EventTable],
    ['展示副本事件表', ShowcaseEventTable],
  ] as const)('%s 卸载后重挂仍然测量表体', (label, Table) => {
    const view = render(
      <div style={{ width: 526, height: 268 }}>
        <Table
          rawData={rows}
          loading={false}
          dataSource={plainSource}
          config={{
            chartType: 'eventTable',
            tableConfig: { columns },
          }}
        />
      </div>,
    );
    expectMeasuredBody(view.container);
    view.unmount();

    const remounted = render(
      <div style={{ width: 526, height: 268 }}>
        <Table
          rawData={rows}
          loading={false}
          dataSource={plainSource}
          config={{
            chartType: 'eventTable',
            tableConfig: { columns },
          }}
        />
      </div>,
    );
    expectMeasuredBody(remounted.container);
    expect(label).toContain('事件表');
  });
});
