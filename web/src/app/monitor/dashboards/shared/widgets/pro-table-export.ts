const INVALID_FILE_CHARS = /[\\/:*?"<>|\u0000-\u001f]+/g;

const filePart = (value: string) => value.trim().replace(INVALID_FILE_CHARS, '').replace(/\s+/g, '');

/** 文件名带对象、页签、表名，三段用连字符接上。 */
export const proTableFileName = (objectName: string, tab: string, table: string) => (
  `${filePart(objectName)}-${filePart(tab)}-${filePart(table)}.csv`
);

const escapeCell = (value: string) => (
  /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value
);

/** 表头 + 当前排序筛选后的行。调用方把合计行放在最后。 */
export const buildProTableCsv = (
  headers: readonly string[],
  rows: readonly (readonly string[])[]
) => [headers, ...rows].map((row) => row.map((cell) => escapeCell(String(cell))).join(',')).join('\r\n');

export const downloadProTableCsv = (
  fileName: string,
  headers: readonly string[],
  rows: readonly (readonly string[])[]
) => {
  if (typeof document === 'undefined') return;
  const csv = `\uFEFF${buildProTableCsv(headers, rows)}`;
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};
