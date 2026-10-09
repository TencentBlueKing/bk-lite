import ExcelJS from 'exceljs';
import { excelCellToText } from '@/utils/excelCellText';

export interface ErrorReportTable {
  columns: string[];
  rows: Record<string, string>[];
}

export async function parseErrorReport(data: ArrayBuffer): Promise<ErrorReportTable> {
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(data);
  const sheet = workbook.worksheets[0];
  if (!sheet) return { columns: [], rows: [] };

  const header = sheet.getRow(1);
  const columns: string[] = [];
  for (let index = 1; index <= header.cellCount; index += 1) {
    const text = excelCellToText(header.getCell(index).value);
    if (text) columns.push(text);
  }

  const rows: Record<string, string>[] = [];
  sheet.eachRow((row, rowNumber) => {
    if (rowNumber === 1) return;
    const record: Record<string, string> = { key: String(rowNumber) };
    let hasValue = false;
    columns.forEach((column, index) => {
      const text = excelCellToText(row.getCell(index + 1).value);
      record[column] = text;
      if (text) hasValue = true;
    });
    if (hasValue) rows.push(record);
  });
  return { columns, rows };
}
