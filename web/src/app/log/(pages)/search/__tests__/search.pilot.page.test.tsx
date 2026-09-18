import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { Spin } from 'antd';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getTextContext } from '../search.pilot';
import SearchTable from '../searchTable';

const SENTINEL = 'checkout timeout visible-log-line';
const DISPLAY_TIME = '2026-09-18 10:00:00';
const HOST_COL = 'host-should-not-appear';
const EXPANDED_KV = 'expanded-kv-should-not-appear';
const BEARER_TOKEN = 'eyJhbGciOiJIUzI1NiJ9.payload';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (value: string) => value,
    timeZone: 'Asia/Shanghai',
  }),
}));

const setSearchView = () => {
  window.history.replaceState({}, '', '/log/search');
};

const segmented = (checked: 'list' | 'overview') => (
  <div className="ant-segmented" role="radiogroup">
    <label className="ant-segmented-item">
      <input
        className="ant-segmented-item-input"
        type="radio"
        defaultChecked={checked === 'list'}
      />
      <div className="ant-segmented-item-label">列表</div>
    </label>
    <label className="ant-segmented-item">
      <input
        className="ant-segmented-item-input"
        type="radio"
        defaultChecked={checked === 'overview'}
      />
      <div className="ant-segmented-item-label">终端</div>
    </label>
  </div>
);

const LogSearchListShell = ({
  view = 'list',
  extraFields = ['host'],
  dataSource,
  scrollY = 400,
  treeSpinning = false,
  tableLoading = false,
}: {
  view?: 'list' | 'overview';
  extraFields?: string[];
  dataSource?: Array<Record<string, string>>;
  scrollY?: number;
  treeSpinning?: boolean;
  tableLoading?: boolean;
}) => (
  <div className="search_x">
    <div className="searchCondition_x">
      <span className="ant-input-affix-wrapper">
        <input className="ant-input" defaultValue="error AND timeout" />
      </span>
    </div>
    {segmented(view)}
    <div className="collapse-title">
      <span>日志总条数：</span>
      <span>1</span>
    </div>
    <div className="tableArea">
      <Spin spinning={treeSpinning}>
        <div className="w-[230px] min-w-[230px] flex-shrink-0">字段树</div>
      </Spin>
      <SearchTable
        loading={tableLoading}
        dataSource={dataSource || [
          {
            id: 'row-1',
            _time: DISPLAY_TIME,
            message: `${SENTINEL} Authorization: Bearer ${BEARER_TOKEN}`,
            host: HOST_COL,
            collector: EXPANDED_KV,
          },
        ]}
        fields={extraFields}
        scroll={{ x: 'max-content', y: scrollY }}
        addToQuery={() => undefined}
      />
    </div>
  </div>
);

const stubLayout = () => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() {
      return 640;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get() {
      return 400;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get() {
      return 640;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get() {
      return 40;
    },
  });
  HTMLElement.prototype.getBoundingClientRect = function getBoundingClientRect() {
    return {
      width: 640,
      height: 40,
      top: 0,
      left: 0,
      bottom: 40,
      right: 640,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    };
  };
};

const originalClientWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth');
const originalClientHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientHeight');
const originalOffsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
const originalGetBoundingClientRect = HTMLElement.prototype.getBoundingClientRect;

const restoreLayout = () => {
  if (originalClientWidth) Object.defineProperty(HTMLElement.prototype, 'clientWidth', originalClientWidth);
  if (originalClientHeight) Object.defineProperty(HTMLElement.prototype, 'clientHeight', originalClientHeight);
  if (originalOffsetWidth) Object.defineProperty(HTMLElement.prototype, 'offsetWidth', originalOffsetWidth);
  if (originalOffsetHeight) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originalOffsetHeight);
  HTMLElement.prototype.getBoundingClientRect = originalGetBoundingClientRect;
};

const visibleMainRowMessages = () =>
  Array.from(document.querySelectorAll('.ant-table-tbody-virtual .ant-table-row'))
    .filter((row) => !row.classList.contains('ant-table-expanded-row'))
    .map((row) => row.textContent || '');

const snapshotText = () =>
  (getTextContext().sections || []).map((section) => section.content).join('\n');

const snapshotMessages = () =>
  getTextContext().sections?.find((section) => section.id === 'log-search-messages')?.content || '';

describe('search.pilot 真实 SearchTable 采集', () => {
  beforeEach(() => {
    stubLayout();
    setSearchView();
  });

  afterEach(() => {
    cleanup();
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    restoreLayout();
  });

  it('把屏上可见主行写入可见日志，跳过其它列与展开行', async () => {
    const user = userEvent.setup();
    render(<LogSearchListShell />);

    expect(screen.getByText(new RegExp(SENTINEL))).not.toBeNull();
    await waitFor(() => {
      expect(document.querySelector('.ant-table-tbody-virtual .ant-table-row')).not.toBeNull();
    });

    const firstTable = document.querySelector('[class*="tableArea"] table');
    expect(firstTable).not.toBeNull();
    expect(firstTable?.querySelectorAll('tbody tr')).toHaveLength(0);
    expect(document.querySelector('.ant-table-tbody-virtual .ant-table-row')?.tagName).toBe('DIV');

    const expand = document.querySelector<HTMLElement>('.ant-table-row-expand-icon');
    expect(expand).not.toBeNull();
    await user.click(expand!);
    expect((await screen.findAllByText(EXPANDED_KV)).length).toBeGreaterThan(0);

    const snapshot = getTextContext();
    const sectionIds = (snapshot.sections || []).map((section) => section.id);
    const messages = snapshot.sections?.find((section) => section.id === 'log-search-messages');
    expect(sectionIds).toContain('log-search-messages');
    expect(messages?.content).toContain(DISPLAY_TIME);
    expect(messages?.content).toContain(SENTINEL);
    expect(messages?.content).toContain('Bearer [已省略]');
    expect(messages?.content).not.toContain(BEARER_TOKEN);
    expect(messages?.content).not.toContain(HOST_COL);
    expect(messages?.content).not.toContain(EXPANDED_KV);
    expect(snapshot.images || []).toEqual([]);
  });

  it('终端模式即使表在 DOM 里也不采集', async () => {
    render(<LogSearchListShell view="overview" />);
    expect(screen.getByText(new RegExp(SENTINEL))).not.toBeNull();
    await waitFor(() => {
      expect(document.querySelector('.ant-table-tbody-virtual .ant-table-row')).not.toBeNull();
    });
    expect(getTextContext().sections || []).toEqual([]);
  });

  it('展开后不注入展开区，只注入当前仍在虚拟列表里的主行', async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: 20 }, (_, index) => ({
      id: `row-${index}`,
      _time: DISPLAY_TIME,
      message: `visible-main-line#${index}#`,
      host: HOST_COL,
      collector: EXPANDED_KV,
    }));
    render(<LogSearchListShell dataSource={rows} scrollY={160} />);
    await waitFor(() => {
      expect(document.querySelector('.ant-table-tbody-virtual .ant-table-row')).not.toBeNull();
    });

    const beforeSnap = snapshotMessages();
    expect(beforeSnap).toContain('visible-main-line#0#');
    expect(beforeSnap).not.toContain('visible-main-line#19#');

    const expand = document.querySelector<HTMLElement>('.ant-table-row-expand-icon');
    expect(expand).not.toBeNull();
    await user.click(expand!);
    expect((await screen.findAllByText(EXPANDED_KV)).length).toBeGreaterThan(0);

    const afterDom = visibleMainRowMessages();
    const afterSnap = snapshotMessages();
    expect(afterSnap).not.toContain(EXPANDED_KV);
    rows.forEach((row) => {
      const stillInDom = afterDom.some((text) => text.includes(row.message));
      if (stillInDom) expect(afterSnap).toContain(row.message);
      else expect(afterSnap).not.toContain(row.message);
    });
  });

  it('字段树在转、表已有可见行时仍注入可见日志', async () => {
    render(<LogSearchListShell treeSpinning />);
    expect(screen.getByText(new RegExp(SENTINEL))).not.toBeNull();
    await waitFor(() => {
      expect(document.querySelector('.ant-table-tbody-virtual .ant-table-row')).not.toBeNull();
    });

    const tableArea = document.querySelector('[class*="tableArea"]');
    const tableSpinRoot = tableArea?.querySelector('.ant-table')?.closest('.ant-spin-nested-loading');
    expect(tableArea?.querySelector('.ant-spin-spinning')).not.toBeNull();
    expect(tableSpinRoot?.querySelector('.ant-spin-spinning')).toBeNull();

    const snapshot = getTextContext();
    const messages = snapshot.sections?.find((section) => section.id === 'log-search-messages');
    expect((snapshot.sections || []).map((section) => section.id)).toContain('log-search-messages');
    expect(messages?.content).toContain(SENTINEL);
    expect(snapshotText()).not.toContain('表格加载中');
  });

  it('SearchTable 自己 loading 时不把字段树当表，也不注入可见日志', async () => {
    render(<LogSearchListShell tableLoading />);
    await waitFor(() => {
      const table = document.querySelector('[class*="tableArea"] .ant-table');
      expect(table?.closest('.ant-spin-nested-loading')?.querySelector('.ant-spin-spinning')).not.toBeNull();
    });

    const snapshot = getTextContext();
    const messages = snapshot.sections?.find((section) => section.id === 'log-search-messages');
    expect(messages).toBeUndefined();
    expect(snapshotText()).toContain('表格加载中');
  });
});
