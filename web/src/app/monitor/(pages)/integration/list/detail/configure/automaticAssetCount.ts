export interface AssetCountColumn {
  name: string;
  required?: boolean;
  is_only?: boolean;
}

type AssetRow = Record<string, unknown>;

const normalizeComparableValue = (value: unknown): unknown => {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (Array.isArray(value)) {
    const normalized = value
      .map(normalizeComparableValue)
      .filter((item) => item !== undefined);
    return normalized.length ? normalized : undefined;
  }
  if (value && typeof value === 'object') {
    const normalized = Object.entries(value).reduce<Record<string, unknown>>(
      (result, [key, item]) => {
        const normalizedItem = normalizeComparableValue(item);
        if (normalizedItem !== undefined) {
          result[key] = normalizedItem;
        }
        return result;
      },
      {}
    );
    return Object.keys(normalized).length ? normalized : undefined;
  }
  return value === null || value === undefined ? undefined : value;
};

const areComparableValuesEqual = (left: unknown, right: unknown): boolean => {
  const normalizedLeft = normalizeComparableValue(left);
  const normalizedRight = normalizeComparableValue(right);
  if (Object.is(normalizedLeft, normalizedRight)) return true;
  if (Array.isArray(normalizedLeft) && Array.isArray(normalizedRight)) {
    return (
      normalizedLeft.length === normalizedRight.length &&
      normalizedLeft.every((item, index) =>
        areComparableValuesEqual(item, normalizedRight[index])
      )
    );
  }
  if (
    normalizedLeft &&
    normalizedRight &&
    typeof normalizedLeft === 'object' &&
    typeof normalizedRight === 'object'
  ) {
    const leftEntries = Object.entries(normalizedLeft);
    const rightEntries = Object.entries(normalizedRight);
    return (
      leftEntries.length === rightEntries.length &&
      leftEntries.every(([key, item]) =>
        areComparableValuesEqual(
          item,
          (normalizedRight as Record<string, unknown>)[key]
        )
      )
    );
  }
  return false;
};

export const hasAssetValue = (value: unknown): boolean =>
  normalizeComparableValue(value) !== undefined;

const getRelevantAssetColumns = (
  visibleColumns: AssetCountColumn[]
): AssetCountColumn[] => {
  const submissionColumns = visibleColumns.filter(
    (column) => column.required || column.is_only
  );
  return submissionColumns.length ? submissionColumns : visibleColumns;
};

export const isCountedAssetRow = (
  row: AssetRow,
  visibleColumns: AssetCountColumn[],
  placeholderRow: AssetRow = {}
): boolean => {
  if (!visibleColumns.length) return false;

  const relevantColumns = getRelevantAssetColumns(visibleColumns);

  const isComplete = relevantColumns.every((column) =>
    hasAssetValue(row[column.name])
  );
  if (!isComplete) return false;

  return relevantColumns.some(
    (column) =>
      !areComparableValuesEqual(
        row[column.name],
        placeholderRow[column.name]
      )
  );
};

/** 仍为初始化默认值/空值的占位行，导入时应剔除，避免空行压在导入数据上方。 */
export const isPlaceholderAssetRow = (
  row: AssetRow,
  visibleColumns: AssetCountColumn[],
  placeholderRow: AssetRow = {}
): boolean => {
  if (!visibleColumns.length) return true;

  const relevantColumns = getRelevantAssetColumns(visibleColumns);
  return relevantColumns.every(
    (column) =>
      !hasAssetValue(row[column.name]) ||
      areComparableValuesEqual(row[column.name], placeholderRow[column.name])
  );
};

/** 保留已填写行，去掉空占位行后追加导入数据。 */
export const mergeImportedAssetRows = <T extends AssetRow>(
  existingRows: T[],
  importedRows: T[],
  visibleColumns: AssetCountColumn[],
  placeholderRow: AssetRow = {}
): T[] => {
  const retainedRows = existingRows.filter(
    (row) => !isPlaceholderAssetRow(row, visibleColumns, placeholderRow)
  );
  return [...retainedRows, ...importedRows];
};

export const countAccessAssets = (
  rows: AssetRow[],
  visibleColumns: AssetCountColumn[],
  placeholderRow: AssetRow = {}
): number =>
  rows.filter((row) =>
    isCountedAssetRow(row, visibleColumns, placeholderRow)
  ).length;
