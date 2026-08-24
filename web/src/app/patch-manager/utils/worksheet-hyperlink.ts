const escapeFormulaString = (value: string) => value.replace(/"/g, '""');

export const buildInternalWorksheetHyperlinkFormula = (
  sheetName: string,
  cellReference: string,
  text: string,
) => {
  const escapedSheetName = sheetName.replace(/'/g, "''");
  return `HYPERLINK("#'${escapedSheetName}'!${cellReference}", "${escapeFormulaString(text)}")`;
};
