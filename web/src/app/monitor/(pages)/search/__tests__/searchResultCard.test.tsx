import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChartItem } from '@/app/monitor/types/search';
import SearchResultCard from '../searchResultCard';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (id: string) => id })
}));
vi.mock('@/app/monitor/hooks/useUnitTransform', () => ({
  useUnitTransform: () => ({ findUnitNameById: () => '' })
}));
vi.mock('@/app/monitor/utils/common', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/app/monitor/utils/common')>();
  return {
    ...actual,
    useFormatTime: () => ({
      formatTime: (time: number) => `t${time}`
    })
  };
});
vi.mock('@/app/monitor/components/charts/lineChart', () => ({
  default: ({
    emphasizedKeys,
    onEmphasizedKeyChange
  }: {
    emphasizedKeys?: string[];
    onEmphasizedKeyChange?: (key: string) => void;
  }) => (
    <div data-testid="line-chart">
      {emphasizedKeys == null ? 'all' : emphasizedKeys.join(',') || 'none'}
      <button type="button" onClick={() => onEmphasizedKeyChange?.('value2')}>
        toggle-line
      </button>
    </div>
  )
}));

const item = {
  groupId: 'g1',
  groupName: '查询条件 1',
  metric: { display_name: '运行中进程数', display_description: '进程数量' },
  data: [
    {
      time: 10,
      value1: 2,
      value2: 9,
      details: {
        value1: [{ name: 'instance_name', label: 'Instance', value: 'web-01' }],
        value2: [{ name: 'instance_name', label: 'Instance', value: 'web-02' }]
      }
    },
    {
      time: 20,
      value1: 6,
      value2: 4,
      details: {
        value1: [{ name: 'instance_name', label: 'Instance', value: 'web-01' }],
        value2: [{ name: 'instance_name', label: 'Instance', value: 'web-02' }]
      }
    }
  ],
  unit: '',
  loading: false,
  duration: 12,
  objectName: '主机',
  aggregation: 'AVG'
} as ChartItem;

describe('搜索结果卡片读法', () => {
  beforeEach(() => {
    window.matchMedia = vi.fn().mockReturnValue({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn()
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('从折线切到组合后，图下面带着序列对比', async () => {
    const user = userEvent.setup();
    const onPresentationChange = vi.fn();
    render(
      <SearchResultCard
        item={item}
        layoutMode="single"
        presentation={{ view: 'line', tableKind: null, emphasizedKeys: null }}
        showApplyAll
        onPresentationChange={onPresentationChange}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );

    expect(screen.getByTestId('line-chart')).toBeTruthy();
    expect(screen.queryByText('monitor.search.table')).toBeNull();
    await user.click(screen.getByText('monitor.search.combo'));
    expect(onPresentationChange).toHaveBeenCalledWith(
      expect.objectContaining({ view: 'combo', tableKind: null })
    );
  });

  it('组合里点一行会突出这条线，并可以导出全部采样', async () => {
    const user = userEvent.setup();
    const onPresentationChange = vi.fn();
    const click = vi.fn();
    const createElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tagName, options) => {
      const element = createElement(tagName, options);
      if (tagName === 'a') element.click = click;
      return element;
    });
    const createObjectURL = vi.fn(() => 'blob:csv');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });

    render(
      <SearchResultCard
        item={item}
        layoutMode="single"
        presentation={{ view: 'combo', tableKind: null, emphasizedKeys: null }}
        showApplyAll={false}
        onPresentationChange={onPresentationChange}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );

    expect(screen.getByTestId('line-chart')).toBeTruthy();
    expect(screen.getByText('monitor.search.seriesCompare')).toBeTruthy();
    expect(screen.getByText('Instance: web-01')).toBeTruthy();
    expect(screen.queryByText(/已突出/)).toBeNull();

    await user.click(screen.getByText('Instance: web-02'));
    expect(onPresentationChange).toHaveBeenCalledWith(
      expect.objectContaining({ emphasizedKeys: ['value2'] })
    );

    await user.click(screen.getByText('monitor.search.sampleDetail'));
    expect(onPresentationChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ tableKind: 'samples' })
    );

    await user.click(screen.getByText('monitor.search.exportCsv'));
    expect(createObjectURL).toHaveBeenCalled();
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    const csv = await blob.text();
    expect(csv).toContain('monitor.search.identifier');
    expect(csv).toContain('Instance: web-01');
    expect(csv).toContain('Instance: web-02');
    expect(click).toHaveBeenCalled();
  });

  it('序列对比染最新值和极差各自的最高、最低', () => {
    render(
      <SearchResultCard
        item={item}
        layoutMode="single"
        presentation={{ view: 'combo', tableKind: 'compare', emphasizedKeys: null }}
        showApplyAll={false}
        onPresentationChange={vi.fn()}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );

    const tones = [...document.querySelectorAll('[data-tone]')].map(
      (node) => `${node.getAttribute('data-tone')}:${node.textContent}`
    );
    expect(tones).toEqual(['low:4.00', 'high:5.00', 'high:6.00', 'low:4.00']);
    expect(seriesActive()).toEqual({ value1: 'true', value2: 'true' });
  });

  it('点中一条后只有它的色杠是实心，再取消后全部恢复', () => {
    const { rerender } = render(
      <SearchResultCard
        item={item}
        layoutMode="single"
        presentation={{ view: 'combo', tableKind: 'compare', emphasizedKeys: ['value2'] }}
        showApplyAll={false}
        onPresentationChange={vi.fn()}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );
    expect(seriesActive()).toEqual({ value1: 'false', value2: 'true' });

    rerender(
      <SearchResultCard
        item={item}
        layoutMode="single"
        presentation={{ view: 'combo', tableKind: 'compare', emphasizedKeys: ['value1', 'value2'] }}
        showApplyAll={false}
        onPresentationChange={vi.fn()}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );
    expect(seriesActive()).toEqual({ value1: 'true', value2: 'true' });
    expect(screen.getByTestId('line-chart').textContent).toContain('value1,value2');

    rerender(
      <SearchResultCard
        item={item}
        layoutMode="single"
        presentation={{ view: 'combo', tableKind: 'compare', emphasizedKeys: null }}
        showApplyAll={false}
        onPresentationChange={vi.fn()}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );
    expect(seriesActive()).toEqual({ value1: 'true', value2: 'true' });
  });

  it('表头可以一次全部激活或全部取消', async () => {
    const user = userEvent.setup();
    const onPresentationChange = vi.fn();
    const { rerender } = render(
      <SearchResultCard
        item={item}
        layoutMode="single"
        presentation={{ view: 'combo', tableKind: 'compare', emphasizedKeys: ['value2'] }}
        showApplyAll={false}
        onPresentationChange={onPresentationChange}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );

    await user.click(screen.getByRole('button', { name: 'monitor.search.deactivateAll' }));
    expect(onPresentationChange).toHaveBeenCalledWith(
      expect.objectContaining({ emphasizedKeys: [] })
    );

    rerender(
      <SearchResultCard
        item={item}
        layoutMode="single"
        presentation={{ view: 'combo', tableKind: 'compare', emphasizedKeys: [] }}
        showApplyAll={false}
        onPresentationChange={onPresentationChange}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );
    expect(seriesActive()).toEqual({ value1: 'false', value2: 'false' });

    await user.click(screen.getByRole('button', { name: 'monitor.search.activateAll' }));
    expect(onPresentationChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ emphasizedKeys: null })
    );
  });

  it('点击折线上的序列，和表格使用同一套激活', async () => {
    const user = userEvent.setup();
    const onPresentationChange = vi.fn();
    render(
      <SearchResultCard
        item={item}
        layoutMode="single"
        presentation={{ view: 'line', tableKind: null, emphasizedKeys: null }}
        showApplyAll={false}
        onPresentationChange={onPresentationChange}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );

    await user.click(screen.getByRole('button', { name: 'toggle-line' }));
    expect(onPresentationChange).toHaveBeenCalledWith(
      expect.objectContaining({ emphasizedKeys: ['value2'] })
    );
  });

  it('采样明细按每列标出最高和最低，并一次只冻结一列', async () => {
    const user = userEvent.setup();
    const sampleItem = {
      ...item,
      data: [
        pointRow(10, 1, 8),
        pointRow(20, 4, 5),
        pointRow(30, 9, 2)
      ]
    };
    render(
      <SearchResultCard
        item={sampleItem}
        layoutMode="single"
        presentation={{ view: 'combo', tableKind: 'samples', emphasizedKeys: null }}
        showApplyAll={false}
        onPresentationChange={vi.fn()}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );

    const tones = [...document.querySelectorAll('[data-tone]')].map(
      (node) => `${node.getAttribute('data-tone')}:${node.textContent}`
    );
    expect(tones).toEqual(['high:9.00', 'low:2.00', 'low:1.00', 'high:8.00']);
    expect(columnKeys()).toEqual(['time', 'value1', 'value2']);
    expect(fixedHeaderKeys()).toEqual(['time']);

    fireEvent.contextMenu(headerCell('value2'));
    await user.click(await screen.findByText('monitor.search.pinColumn'));
    expect(columnKeys()).toEqual(['time', 'value2', 'value1']);
    expect(fixedHeaderKeys()).toEqual(['time', 'value2']);

    fireEvent.contextMenu(headerCell('value1'));
    await user.click(await screen.findByText('monitor.search.pinColumn'));
    expect(columnKeys()).toEqual(['time', 'value1', 'value2']);

    fireEvent.contextMenu(headerCell('value1'));
    await user.click(await screen.findByText('monitor.search.unpinColumn'));
    expect(columnKeys()).toEqual(['time', 'value1', 'value2']);
    expect(fixedHeaderKeys()).toEqual(['time']);
  });

  it('拖动表头可以改变列宽', () => {
    render(
      <SearchResultCard
        item={item}
        layoutMode="single"
        presentation={{ view: 'combo', tableKind: 'compare', emphasizedKeys: null }}
        showApplyAll={false}
        onPresentationChange={vi.fn()}
        onApplyAll={vi.fn()}
        onXRangeChange={vi.fn()}
      />
    );

    const handle = document.querySelector('[role="separator"]');
    expect(handle).toBeTruthy();
    const col = () => document.querySelector('.ant-table colgroup col');
    fireEvent.mouseDown(handle as Element, { clientX: 100 });
    fireEvent.mouseMove(document, { clientX: 180 });
    fireEvent.mouseUp(document);
    expect(col()?.getAttribute('style') || '').toContain('400');
  });
});

const pointRow = (time: number, value1: number, value2: number) => ({
  time,
  value1,
  value2,
  details: {
    value1: [{ name: 'instance_name', label: 'Instance', value: 'web-01' }],
    value2: [{ name: 'instance_name', label: 'Instance', value: 'web-02' }]
  }
});

const fixedHeaderKeys = () => {
  const keys = [...document.querySelectorAll('.ant-table-thead .ant-table-cell-fix-left[data-column-key]')]
    .map((cell) => cell.getAttribute('data-column-key'));
  return keys.filter((key, index) => keys.indexOf(key) === index);
};

const columnKeys = () => {
  const rows = [...document.querySelectorAll('.ant-table-thead tr')];
  const keys = rows.map((row) =>
    [...row.querySelectorAll('[data-column-key]')].map((cell) => cell.getAttribute('data-column-key'))
  );
  return keys.find((row) => row.includes('time')) ?? keys[0] ?? [];
};

const headerCell = (key: string) =>
  document.querySelector(`[data-column-key="${key}"]`) as HTMLElement | null;

const seriesActive = () =>
  Object.fromEntries(
    [...document.querySelectorAll('[data-series-key]')].map((node) => [
      node.getAttribute('data-series-key'),
      node.getAttribute('data-series-active')
    ])
  );
