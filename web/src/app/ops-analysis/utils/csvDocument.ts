import { formatOpsDisplayTime } from '@/app/ops-analysis/utils/dateTime';

const FORMULA_LEAD = /^[\t\r\n ]*[=+\-@]/;
const PURE_NUMBER = /^[\t\r\n ]*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?%?$/;
const ILLEGAL_FILENAME = /[\\/:*?"<>|\u0000-\u001f]/g;

export const sanitizeCsvCell = (value: unknown): string => {
  const text = value == null ? '' : String(value);
  if (PURE_NUMBER.test(text)) return text;
  return FORMULA_LEAD.test(text) ? `'${text}` : text;
};

export const escapeCsvCell = (value: unknown): string => {
  const text = sanitizeCsvCell(value);
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
};

export const buildCsvDocument = (headers: string[], rows: string[][]): string => {
  const lines = [headers, ...rows].map((row) => row.map((cell) => escapeCsvCell(cell)).join(','));
  return `\uFEFF${lines.join('\r\n')}`;
};

export const buildCsvFilename = (title: string, now: Date = new Date()): string => {
  const cleaned = title.trim().replace(ILLEGAL_FILENAME, '_').replace(/\s+/g, ' ');
  const base = cleaned || 'export';
  const stamp = formatOpsDisplayTime(now.getTime(), 'YYYYMMDD-HHmmss');
  return `${base}-${stamp}.csv`;
};

export const downloadCsvFile = (filename: string, csv: string): void => {
  if (typeof document === 'undefined') return;
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
};
