'use client';

import { DownloadOutlined } from '@ant-design/icons';
import { Button, Dropdown } from 'antd';

import { useTranslation } from '@/utils/i18n';

function rowsToCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return '';
  const headers = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return `\uFEFF${[headers.join(','), ...rows.map((r) => headers.map((h) => esc(r[h])).join(','))].join('\n')}`;
}

function download(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function exportRowsToCsv(rows: Record<string, unknown>[]): string {
  return rowsToCsv(rows);
}

export default function ExportButton({
  rows,
  filename,
  truncated,
  truncatedLimit,
}: {
  rows: Record<string, unknown>[];
  filename: string;
  truncated?: boolean;
  truncatedLimit?: number;
}) {
  const { t } = useTranslation();
  const disabled = !rows.length;
  const limit = truncatedLimit ?? 1000;
  const exportRows = truncated ? rows.slice(0, limit) : rows;

  function doExport(kind: 'csv' | 'json') {
    if (kind === 'csv') {
      download(`${filename}.csv`, rowsToCsv(exportRows), 'text/csv;charset=utf-8');
    } else {
      download(`${filename}.json`, JSON.stringify(exportRows, null, 2), 'application/json;charset=utf-8');
    }
  }

  return (
    <Dropdown
      trigger={['click']}
      disabled={disabled}
      menu={{
        onClick: ({ key }) => doExport(key as 'csv' | 'json'),
        items: [
          { key: 'csv', label: t('rum.export.csv', '导出 CSV') },
          { key: 'json', label: t('rum.export.json', '导出 JSON') },
        ],
      }}
    >
      <Button
        icon={<DownloadOutlined aria-hidden="true" />}
        disabled={disabled}
        aria-label={t('rum.export.csv', '导出')}
        title={
          truncated
            ? t('rum.export.truncated', '仅导出前 {n} 行', { n: limit })
            : undefined
        }
      >
        {t('rum.export.label', '导出')}
      </Button>
    </Dropdown>
  );
}
