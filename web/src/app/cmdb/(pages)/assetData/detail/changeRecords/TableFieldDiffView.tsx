'use client';

import React, { useMemo, useState } from 'react';

import { useTranslation } from '@/utils/i18n';
import type {
  TableCellDiff,
  TableFieldDiff,
  TableRowDiff,
} from './changeRecordTypes';

const PAGE_SIZE = 50;

interface TableFieldDiffViewProps {
  diff: TableFieldDiff;
  compact?: boolean;
}

interface VisibleCellDiff extends TableCellDiff {
  key: string;
  rowLabel: string;
  rowStatus: TableRowDiff['status'];
}

const rowNumber = (row: TableRowDiff) => {
  const index = row.afterIndex ?? row.beforeIndex ?? row.currentIndex ?? 0;
  return index + 1;
};

const wholeRowValue = (
  row: TableRowDiff,
  field: 'before' | 'after' | 'current'
) => row.cells.map((cell) => `${cell.columnName}：${cell[field]}`).join('；');

const toVisibleCells = (
  rows: TableRowDiff[],
  showAll: boolean,
  labels: {
    row: (row: number) => string;
    wholeRow: string;
    rowPosition: string;
  }
): VisibleCellDiff[] =>
  rows.flatMap((row) => {
    if (row.status === 'ambiguous') {
      return [
        {
          key: `${row.key}:whole-row`,
          rowLabel: labels.row(rowNumber(row)),
          rowStatus: row.status,
          columnId: '__row__',
          columnName: labels.wholeRow,
          before: wholeRowValue(row, 'before'),
          after: wholeRowValue(row, 'after'),
          current: wholeRowValue(row, 'current'),
          changed: true,
          currentDiff: row.cells.some((cell) => cell.currentDiff),
        },
      ];
    }
    if (row.status === 'moved' && !showAll) {
      return [
        {
          key: `${row.key}:moved`,
          rowLabel: labels.row(rowNumber(row)),
          rowStatus: row.status,
          columnId: '__moved__',
          columnName: labels.rowPosition,
          before: labels.row((row.beforeIndex ?? 0) + 1),
          after: labels.row((row.afterIndex ?? 0) + 1),
          current: labels.row((row.currentIndex ?? row.afterIndex ?? 0) + 1),
          changed: false,
          currentDiff: row.currentIndex !== row.afterIndex,
        },
      ];
    }
    return row.cells
      .filter(
        (cell) =>
          showAll ||
          cell.changed ||
          cell.currentDiff ||
          row.status === 'added' ||
          row.status === 'removed'
      )
      .map((cell) => ({
        ...cell,
        key: `${row.key}:${cell.columnId}`,
        rowLabel: labels.row(rowNumber(row)),
        rowStatus: row.status,
      }));
  });

const TableFieldDiffView: React.FC<TableFieldDiffViewProps> = ({
  diff,
  compact = false,
}) => {
  const { t } = useTranslation();
  const [showAll, setShowAll] = useState(false);
  const [page, setPage] = useState(1);
  const visibleCells = useMemo(
    () =>
      toVisibleCells(diff.rows, showAll, {
        row: (row) =>
          t('Model.changeRecord.rowNumber', '第 {row} 行', { row }),
        wholeRow: t('Model.changeRecord.wholeRow', '整行'),
        rowPosition: t('Model.changeRecord.rowPosition', '行位置'),
      }),
    [diff.rows, showAll, t]
  );
  const pageCount = Math.max(1, Math.ceil(visibleCells.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pagedCells = visibleCells.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE
  );
  const changedRows = diff.rows.filter((row) => row.status !== 'unchanged').length;
  const matchLabel =
    diff.matchMode === 'row-key'
      ? t('Model.changeRecord.rowKeyMatch', '按行标识匹配')
      : diff.matchMode === 'row-level'
        ? t('Model.changeRecord.rowLevelMatch', '仅识别到行级差异')
        : t('Model.changeRecord.positionMatch', '按行号匹配');

  return (
    <div className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg)]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-[var(--color-text-1)]">
            {t(
              'Model.changeRecord.tableDiffSummary',
              '修改 {rows} 行、{cells} 个单元格',
              { rows: changedRows, cells: diff.summary.changedCells }
            )}
          </span>
          <span className="rounded bg-[var(--color-fill-2)] px-2 py-0.5 text-[var(--color-text-3)]">
            {matchLabel}
          </span>
        </div>
        {!compact && (
          <button
            type="button"
            className="cursor-pointer border-0 bg-transparent text-[var(--color-primary)]"
            onClick={() => {
              setShowAll((value) => !value);
              setPage(1);
            }}
          >
            {showAll
              ? t('Model.changeRecord.showChangedCells', '仅显示变化单元格')
              : t('Model.changeRecord.showAllCells', '显示全部单元格')}
          </button>
        )}
      </div>
      <div className="w-full">
        <table className="w-full table-auto border-collapse text-left text-xs">
          <thead className="bg-[var(--color-fill-1)] text-[var(--color-text-2)]">
            <tr>
              <th className="break-words px-2 py-2">{t('Model.changeRecord.row', '行')}</th>
              <th className="break-words px-2 py-2">{t('Model.changeRecord.column', '列')}</th>
              <th className="break-words px-2 py-2">{t('Model.beforeTheChange')}</th>
              <th className="break-words px-2 py-2">{t('Model.afterTheChange')}</th>
              <th className="break-words px-2 py-2">{t('Model.changeRecord.current')}</th>
            </tr>
          </thead>
          <tbody>
            {pagedCells.map((cell) => (
              <tr key={cell.key} className="border-t border-[var(--color-border)] align-top">
                <td className="break-all px-2 py-2 text-[var(--color-text-2)]">{cell.rowLabel}</td>
                <td className="break-all px-2 py-2 font-medium text-[var(--color-text-1)]">{cell.columnName}</td>
                <td className={cell.changed ? 'break-all px-2 py-2 text-[var(--color-error)]' : 'break-all px-2 py-2 text-[var(--color-text-1)]'}>
                  {cell.before}
                </td>
                <td className={cell.changed ? 'break-all px-2 py-2 font-medium text-[var(--color-success)]' : 'break-all px-2 py-2 text-[var(--color-text-1)]'}>
                  {cell.after}
                </td>
                <td className={cell.currentDiff ? 'break-all px-2 py-2 font-medium text-[var(--color-warning)]' : 'break-all px-2 py-2 text-[var(--color-text-1)]'}>
                  {cell.current}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {visibleCells.length > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-2 border-t border-[var(--color-border)] px-3 py-2">
          <button
            type="button"
            disabled={safePage <= 1}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
          >
            {t('previousPage', '上一页')}
          </button>
          <span className="text-[var(--color-text-3)]">{safePage} / {pageCount}</span>
          <button
            type="button"
            disabled={safePage >= pageCount}
            onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
          >
            {t('nextPage', '下一页')}
          </button>
        </div>
      )}
    </div>
  );
};

export default TableFieldDiffView;
