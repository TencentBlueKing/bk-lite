'use client';

import React from 'react';
import { DownloadOutlined } from '@ant-design/icons';
import { Button, message } from 'antd';
import type { EntityTableRow } from '../entity-series';
import { layeredColumnText, type LayeredColumn } from './entity-table';
import { buildCsvDocument, buildCsvFilename } from './table-csv';

const downloadCsv = (filename: string, content: string) => {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

export function exportEntityRowsToCsv({
  host,
  slug,
  columns,
  rows,
  now = new Date()
}: {
  host: string;
  slug: string;
  columns: LayeredColumn[];
  rows: EntityTableRow[];
  now?: Date;
}) {
  if (!rows.length) {
    message.info('暂无数据可导出');
    return;
  }
  const headers = columns.map((column) => column.title);
  const body = rows.map((row) => columns.map((column) => layeredColumnText(column, row)));
  downloadCsv(buildCsvFilename(host, slug, now), buildCsvDocument(headers, body));
}

export default function TableCsvExportButton({
  host,
  slug,
  columns,
  rows
}: {
  host: string;
  slug: string;
  columns: LayeredColumn[];
  rows: EntityTableRow[];
}) {
  return (
    <Button
      type="text"
      size="small"
      icon={<DownloadOutlined aria-hidden="true" />}
      className="!h-auto shrink-0 !px-1 !text-[13px] !text-[var(--color-text-2)] hover:!text-[var(--color-primary)]"
      onClick={() => exportEntityRowsToCsv({ host, slug, columns, rows })}
    >
      导出 CSV
    </Button>
  );
}
