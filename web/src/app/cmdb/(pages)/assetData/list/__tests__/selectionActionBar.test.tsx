import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, expect, it, vi } from 'vitest';
import SelectionActionBar from '../selectionActionBar';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (id: string) =>
      ({
        'common.checked': '已选',
        'common.items': '项',
        batchEdit: '批量编辑',
        export: '导出',
        'Model.systemLinkageBatchSync': '建立监控关联',
        'common.batchDelete': '批量删除',
        selectionBarClear: '取消选择',
        'subscription.subscribe': '订阅',
      })[id] ?? id,
  }),
}));

vi.mock('@/components/permission', () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}));

const here = dirname(fileURLToPath(import.meta.url));

afterEach(cleanup);

const renderBar = (overrides: Partial<React.ComponentProps<typeof SelectionActionBar>> = {}) => {
  const props = {
    count: 2,
    canBatchEdit: true,
    showMonitorLink: false,
    onBatchEdit: vi.fn(),
    onExport: vi.fn(),
    onSubscribe: vi.fn(),
    onMonitorLink: vi.fn(),
    onDelete: vi.fn(),
    onClear: vi.fn(),
    ...overrides,
  };
  render(<SelectionActionBar {...props} />);
  return props;
};

it('stays hidden until at least one instance is selected', () => {
  renderBar({ count: 0 });
  expect(screen.queryByRole('toolbar')).toBeNull();
});

it('offers the existing batch actions for the current selection', () => {
  const props = renderBar();

  expect(screen.getByRole('toolbar', { name: '已选 2 项' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '批量编辑' }));
  fireEvent.click(screen.getByRole('button', { name: '导出' }));
  fireEvent.click(screen.getByRole('button', { name: '订阅' }));
  fireEvent.click(screen.getByRole('button', { name: '批量删除' }));
  fireEvent.click(screen.getByRole('button', { name: '取消选择' }));

  expect(props.onBatchEdit).toHaveBeenCalledOnce();
  expect(props.onExport).toHaveBeenCalledOnce();
  expect(props.onSubscribe).toHaveBeenCalledOnce();
  expect(props.onDelete).toHaveBeenCalledOnce();
  expect(props.onClear).toHaveBeenCalledOnce();
  expect(screen.queryByRole('button', { name: '建立监控关联' })).toBeNull();
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('shows monitor linking only when the current model supports it', () => {
  const props = renderBar({ showMonitorLink: true });
  fireEvent.click(screen.getByRole('button', { name: '建立监控关联' }));
  expect(props.onMonitorLink).toHaveBeenCalledOnce();
});

it('does not start a batch edit when attributes are unavailable', () => {
  const props = renderBar({ canBatchEdit: false });
  const edit = screen.getByRole('button', { name: '批量编辑' });
  expect(edit).toHaveProperty('disabled', true);
  fireEvent.click(edit);
  expect(props.onBatchEdit).not.toHaveBeenCalled();
});

it('keeps the bar as a shortcut into the existing list handlers', () => {
  const pageSource = readFileSync(resolve(here, '../../page.tsx'), 'utf8');
  const barSource = readFileSync(resolve(here, '../selectionActionBar.tsx'), 'utf8');
  const start = pageSource.indexOf('<SelectionActionBar');
  const end = pageSource.indexOf('/>', start);
  const usage = pageSource.slice(start, end);

  expect(start).toBeGreaterThan(-1);
  expect(usage).toContain('onDelete={batchDeleteConfirm}');
  expect(usage).toContain("onBatchEdit={() => showAttrModal('batchEdit')}");
  expect(usage).toContain("handleExport('selected')");
  expect(usage).toContain("onSubscribe={() => openSubscription('list_selection')}");
  expect(usage).toContain('onMonitorLink={batchSyncMonitorConfirm}');
  expect(pageSource).toContain("onSubscribe={() => openSubscription('list_filter')}");
  expect(usage).toContain('onClear={() => setSelectedRowKeys([])}');
  expect(barSource).not.toContain('Modal');
});
