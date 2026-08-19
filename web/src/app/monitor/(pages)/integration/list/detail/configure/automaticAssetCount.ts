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

export const isCountedAssetRow = (
  row: AssetRow,
  visibleColumns: AssetCountColumn[],
  placeholderRow: AssetRow = {}
): boolean => {
  if (!visibleColumns.length) return false;

  const submissionColumns = visibleColumns.filter(
    (column) => column.required || column.is_only
  );
  const relevantColumns = submissionColumns.length
    ? submissionColumns
    : visibleColumns;

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

export const countAccessAssets = (
  rows: AssetRow[],
  visibleColumns: AssetCountColumn[],
  placeholderRow: AssetRow = {}
): number =>
  rows.filter((row) =>
    isCountedAssetRow(row, visibleColumns, placeholderRow)
  ).length;
