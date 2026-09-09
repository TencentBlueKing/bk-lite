import type ExcelJS from 'exceljs';

export const EXCEL_TEMPLATE_DATA_END_ROW = 1001;
const EXCEL_SHEET_NAME_MAX = 31;
const INVALID_SHEET_CHARS = /[\\/*?:[\]]/g;

type WorksheetWithValidations = ExcelJS.Worksheet & {
  dataValidations: {
    add: (address: string, validation: ExcelJS.DataValidation) => void;
  };
};

export function excelColumnLetter(index: number): string {
  let n = index + 1;
  let letter = '';
  while (n > 0) {
    const rem = (n - 1) % 26;
    letter = String.fromCharCode(65 + rem) + letter;
    n = Math.floor((n - 1) / 26);
  }
  return letter;
}

export function sanitizeExcelSheetName(name: string): string {
  return (
    name
      .replace(INVALID_SHEET_CHARS, '_')
      .replace(/^'+|'+$/g, '')
      .trim()
      .slice(0, EXCEL_SHEET_NAME_MAX) || 'Options'
  );
}

export function uniqueExcelSheetName(
  workbook: ExcelJS.Workbook,
  desiredName: string
): string {
  const baseName = sanitizeExcelSheetName(desiredName);
  let candidate = baseName;
  let counter = 1;
  while (workbook.getWorksheet(candidate)) {
    const suffix = `_${counter}`;
    candidate = `${baseName.slice(0, EXCEL_SHEET_NAME_MAX - suffix.length)}${suffix}`;
    counter += 1;
  }
  return candidate;
}

export function quoteExcelSheetName(name: string): string {
  return `'${name.replace(/'/g, "''")}'`;
}

export function addExcelOptionSheet(
  workbook: ExcelJS.Workbook,
  desiredName: string,
  options: string[]
): string {
  const sheetName = uniqueExcelSheetName(workbook, desiredName);
  const optionsSheet = workbook.addWorksheet(sheetName);
  options.forEach((opt) => {
    optionsSheet.addRow([opt]);
  });
  optionsSheet.getColumn(1).width = 30;
  return sheetName;
}

export function applyExcelRangeValidation(
  worksheet: ExcelJS.Worksheet,
  sqref: string,
  validation: ExcelJS.DataValidation
): void {
  (worksheet as WorksheetWithValidations).dataValidations.add(sqref, validation);
}

export function applyExcelListValidation(
  worksheet: ExcelJS.Worksheet,
  columnIndex: number,
  optionSheetName: string,
  optionCount: number,
  extras: {
    allowBlank: boolean;
    showErrorMessage?: boolean;
    errorTitle?: string;
    error?: string;
    promptTitle?: string;
    showInputMessage?: boolean;
    startRow?: number;
    endRow?: number;
  }
): void {
  const columnLetter = excelColumnLetter(columnIndex);
  const startRow = extras.startRow ?? 2;
  const endRow = extras.endRow ?? EXCEL_TEMPLATE_DATA_END_ROW;
  applyExcelRangeValidation(worksheet, `${columnLetter}${startRow}:${columnLetter}${endRow}`, {
    type: 'list',
    allowBlank: extras.allowBlank,
    formulae: [`${quoteExcelSheetName(optionSheetName)}!$A$1:$A$${optionCount}`],
    showErrorMessage: extras.showErrorMessage ?? true,
    errorTitle: extras.errorTitle,
    error: extras.error,
    promptTitle: extras.promptTitle,
    showInputMessage: extras.showInputMessage ?? true,
  });
}
