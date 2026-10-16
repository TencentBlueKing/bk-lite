/** 主机专业仪表盘表格导出。非法文件名字符换成下划线，UTF-8 带 BOM。 */

const ILLEGAL_FILENAME = /[/\\:*?"<>|\s]/g;

export const sanitizeCsvHost = (value: string) => {
  const replaced = String(value || '').replace(ILLEGAL_FILENAME, '_');
  return replaced || 'host';
};

export const formatCsvStamp = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, '0');
  return [
    `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}`,
    `${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
  ].join('_');
};

export const buildCsvFilename = (host: string, slug: string, date = new Date()) => (
  `${sanitizeCsvHost(host)}_${slug}_${formatCsvStamp(date)}.csv`
);

export const escapeCsvCell = (value: string) => {
  if (/[",\n\r]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
  return value;
};

export const buildCsvDocument = (headers: string[], rows: string[][]) => {
  const lines = [
    headers.map(escapeCsvCell).join(','),
    ...rows.map((row) => row.map(escapeCsvCell).join(','))
  ];
  return `\uFEFF${lines.join('\n')}`;
};
