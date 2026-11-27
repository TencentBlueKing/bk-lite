'use client';

import type { ReactNode } from 'react';
import { downloadProTableCsv, proTableFileName } from './pro-table-export';

export interface ProMetricColumn {
  key: string;
  label: string;
  align?: 'left' | 'right';
  minWidth?: number;
}

export interface ProMetricRow {
  key: string;
  cells: readonly ReactNode[];
  csv: readonly string[];
  variant?: 'body' | 'group';
}

const CELL = 'border-b border-r border-[var(--color-border)] px-2 py-2 last:border-r-0';

/**
 * 专业盘列表表：灰表头、行列线、表头吸顶、合计行吸底，右上角导出当前排序和筛选。
 * 本轮只由 Nginx 接入。
 */
export function ProMetricTable({
  id,
  title,
  hint,
  extra,
  objectName,
  tabName,
  tableName,
  columns,
  rows,
  footer,
  heightClass,
  onSort,
  empty
}: {
  id?: string;
  title: ReactNode;
  hint?: ReactNode;
  extra?: ReactNode;
  objectName: string;
  tabName: string;
  tableName: string;
  columns: readonly ProMetricColumn[];
  rows: readonly ProMetricRow[];
  footer?: ProMetricRow | null;
  heightClass: string;
  onSort?: (key: string) => void;
  empty?: ReactNode;
}) {
  const fileName = proTableFileName(objectName, tabName, tableName);
  const headers = columns.map((column) => column.label);
  const csvRows = [
    ...rows.map((row) => row.csv),
    ...(footer ? [footer.csv] : [])
  ];
  return (
    <section
      className={`flex flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] ${heightClass}`}
      id={id}
      data-pro-table={tableName}
    >
      <div className="flex items-center justify-between gap-3 px-3 pt-3">
        <div className="inline-flex min-w-0 items-center gap-1 text-[14px] font-semibold text-[var(--color-text-1)]">
          {title}
          {hint}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {extra}
          <button
            type="button"
            className="text-[13px] text-[var(--color-primary)]"
            data-pro-table-export=""
            data-export-name={fileName}
            onClick={() => downloadProTableCsv(fileName, headers, csvRows)}
          >
            导出
          </button>
        </div>
      </div>
      {empty ?? (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead className="sticky top-0 z-10">
              <tr className="bg-[var(--color-fill-2)] text-[var(--color-text-2)]">
                {columns.map((column) => (
                  <th
                    key={column.key}
                    className={`${CELL} font-semibold ${column.align === 'right' ? 'text-right' : 'text-left'}`}
                    style={column.minWidth ? { minWidth: column.minWidth } : undefined}
                  >
                    {onSort ? (
                      <button type="button" className="font-semibold text-[var(--color-text-2)]" onClick={() => onSort(column.key)}>
                        {column.label}
                      </button>
                    ) : column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.key}
                  className={row.variant === 'group' ? 'bg-[var(--color-fill-1)] font-semibold' : 'bg-[var(--color-bg)]'}
                  data-pro-table-row={row.variant === 'group' ? 'group' : 'body'}
                  data-row-key={row.key}
                >
                  {row.cells.map((cell, index) => (
                    <td
                      key={columns[index]?.key ?? index}
                      className={`${CELL} ${columns[index]?.align === 'right' ? 'text-right tabular-nums' : 'text-left'}`}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            {footer ? (
              <tfoot className="sticky bottom-0 z-10">
                <tr className="border-t border-[var(--color-border)] bg-[var(--color-fill-2)] font-semibold" data-pro-table-row="total" data-row-key={footer.key}>
                  {footer.cells.map((cell, index) => (
                    <td
                      key={columns[index]?.key ?? index}
                      className={`${CELL} ${columns[index]?.align === 'right' ? 'text-right tabular-nums' : 'text-left'}`}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              </tfoot>
            ) : null}
          </table>
        </div>
      )}
    </section>
  );
}
