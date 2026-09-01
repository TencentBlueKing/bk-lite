import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import TableFieldDiffView from '../TableFieldDiffView';
import type { TableFieldDiff } from '../changeRecordTypes';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, _defaultMessage?: string, values?: Record<string, unknown>) =>
      ({
        'Model.changeRecord.tableDiffSummary': '修改 1 行、1 个单元格',
        'Model.changeRecord.positionMatch': '按行号匹配',
        'Model.changeRecord.rowKeyMatch': '按行标识匹配',
        'Model.changeRecord.rowLevelMatch': '仅识别到行级差异',
        'Model.changeRecord.showAllCells': '显示全部单元格',
        'Model.changeRecord.showChangedCells': '仅显示变化单元格',
        'Model.changeRecord.row': '行',
        'Model.changeRecord.column': '列',
        'Model.changeRecord.rowNumber': `第 ${values?.row} 行`,
        'Model.changeRecord.wholeRow': '整行',
        'Model.changeRecord.rowPosition': '行位置',
        'Model.beforeTheChange': '变更前',
        'Model.afterTheChange': '变更后',
        'Model.changeRecord.current': '当前',
      })[key] || key,
  }),
}));

afterEach(cleanup);

describe('TableFieldDiffView', () => {
  it('展示变化单元格的行、列和前后当前值', () => {
    const diff: TableFieldDiff = {
      matchMode: 'position',
      rows: [
        {
          key: 'position:0',
          beforeIndex: 0,
          afterIndex: 0,
          currentIndex: 0,
          status: 'modified',
          cells: [
            {
              columnId: 'name',
              columnName: '名称',
              before: 'eth0',
              after: 'eth0',
              current: 'eth0',
              changed: false,
              currentDiff: false,
            },
            {
              columnId: 'ip',
              columnName: 'IP 地址',
              before: '10.0.0.1',
              after: '10.0.0.2',
              current: '10.0.0.3',
              changed: true,
              currentDiff: true,
            },
          ],
        },
      ],
      summary: {
        addedRows: 0,
        removedRows: 0,
        modifiedRows: 1,
        changedCells: 1,
      },
    };

    render(<TableFieldDiffView diff={diff} />);

    expect(screen.getByText('修改 1 行、1 个单元格')).not.toBeNull();
    expect(screen.getByText('按行号匹配')).not.toBeNull();
    expect(screen.getByText('第 1 行')).not.toBeNull();
    expect(screen.getByText('IP 地址')).not.toBeNull();
    expect(screen.getByText('10.0.0.1')).not.toBeNull();
    expect(screen.getByText('10.0.0.2')).not.toBeNull();
    expect(screen.getByText('10.0.0.3')).not.toBeNull();
    expect(screen.queryByText('名称')).toBeNull();
  });

  it('窄侧栏使用自适应表格且不创建嵌套横向滚动', () => {
    const diff: TableFieldDiff = {
      matchMode: 'position',
      rows: [],
      summary: {
        addedRows: 0,
        removedRows: 0,
        modifiedRows: 0,
        changedCells: 0,
      },
    };

    const { container } = render(<TableFieldDiffView diff={diff} />);
    const table = screen.getByRole('table');

    expect(container.firstElementChild?.className).not.toContain('min-w-');
    expect(table.className).toContain('table-auto');
    expect(table.parentElement?.className).not.toContain('overflow-x-auto');
  });
});
