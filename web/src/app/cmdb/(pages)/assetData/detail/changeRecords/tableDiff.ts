import type {
  ChangeRecordAttribute,
  TableCellDiff,
  TableColumn,
  TableFieldDiff,
  TableRowDiff,
  TableRowDiffStatus,
} from './changeRecordTypes';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const stableSerialize = (value: unknown): string => {
  if (Array.isArray(value)) {
    return `[${value.map(stableSerialize).join(',')}]`;
  }
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableSerialize(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value) ?? String(value);
};

const isEmptyTableCell = (value: unknown): boolean =>
  value === undefined || value === null || value === '';

const normalizeTableCellForComparison = (value: unknown): unknown =>
  isEmptyTableCell(value) ? '' : value;

const normalizeTableRowForComparison = (
  row: Record<string, unknown>
): Record<string, unknown> =>
  Object.fromEntries(
    Object.entries(row)
      .filter(([, value]) => !isEmptyTableCell(value))
      .map(([key, value]) => [key, normalizeTableCellForComparison(value)])
  );

const tableCellValuesEqual = (left: unknown, right: unknown): boolean =>
  stableSerialize(normalizeTableCellForComparison(left)) ===
  stableSerialize(normalizeTableCellForComparison(right));

const tableRowSignature = (row: Record<string, unknown>): string =>
  stableSerialize(normalizeTableRowForComparison(row));

const parseTableRows = (value: unknown): unknown[] | null => {
  let parsed = value;
  if (typeof value === 'string') {
    try {
      parsed = JSON.parse(value);
    } catch {
      return null;
    }
  }

  if (Array.isArray(parsed)) return parsed;
  return isRecord(parsed) ? [parsed] : null;
};

export const getTableColumns = (attribute?: ChangeRecordAttribute): TableColumn[] => {
  if (!Array.isArray(attribute?.option)) return [];

  return attribute.option
    .filter(
      (column): column is TableColumn =>
        isRecord(column) && typeof column.column_id === 'string'
    )
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
};

const parseLegacyTableRows = (
  value: unknown
): Record<string, unknown>[] | null => {
  let parsed = value;
  if (typeof value === 'string') {
    try {
      parsed = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (!Array.isArray(parsed) || parsed.some((row) => !isRecord(row))) {
    return null;
  }
  return parsed as Record<string, unknown>[];
};

export const inferTableAttribute = (
  ...values: unknown[]
): ChangeRecordAttribute | undefined => {
  const columns = new Map<string, TableColumn>();
  let recognizedTable = false;

  values.forEach((value) => {
    const rows = parseLegacyTableRows(value);
    if (!rows) return;
    recognizedTable = true;
    rows.forEach((row) => {
      Object.keys(row).forEach((columnId) => {
        if (!columns.has(columnId)) {
          columns.set(columnId, {
            column_id: columnId,
            column_name: columnId,
            order: columns.size + 1,
          });
        }
      });
    });
  });

  if (!recognizedTable || columns.size === 0) return undefined;
  return { attr_type: 'table', option: Array.from(columns.values()) };
};

const formatNestedValue = (value: unknown): string => {
  if (value === undefined || value === null || value === '') return '--';
  if (typeof value === 'object') return stableSerialize(value);
  return String(value);
};

export const formatChangeRecordValue = (
  value: unknown,
  attribute?: ChangeRecordAttribute
): string => {
  if (value === undefined || value === null || value === '') return '--';

  if (attribute?.attr_type === 'table') {
    const rows = parseTableRows(value);
    if (rows) {
      if (rows.length === 0) return '--';

      const columns = getTableColumns(attribute);
      return rows
        .map((row) => {
          if (!isRecord(row)) return formatNestedValue(row);
          if (!columns.length) return stableSerialize(row);

          return columns
            .map((column) => {
              const label = column.column_name || column.column_id;
              return `${label}：${formatNestedValue(row[column.column_id])}`;
            })
            .join('；');
        })
        .join('\n');
    }
  }

  if (typeof value === 'object') return stableSerialize(value);
  return String(value);
};

const normalizeForComparison = (
  value: unknown,
  attribute?: ChangeRecordAttribute
): unknown => {
  if (value === undefined || value === null || value === '') return null;
  if (attribute?.attr_type !== 'table') return value;

  const rows = parseTableRows(value);
  if (!rows?.length) return null;
  return rows.map((row) =>
    isRecord(row)
      ? normalizeTableRowForComparison(row)
      : normalizeTableCellForComparison(row)
  );
};

export const valuesEqual = (
  left: unknown,
  right: unknown,
  attribute?: ChangeRecordAttribute
): boolean =>
  stableSerialize(normalizeForComparison(left, attribute)) ===
  stableSerialize(normalizeForComparison(right, attribute));

const tableRowsOrEmpty = (value: unknown): Record<string, unknown>[] | null => {
  if (value === undefined || value === null || value === '') return [];
  const rows = parseTableRows(value);
  if (!rows || rows.some((row) => !isRecord(row))) return null;
  return rows as Record<string, unknown>[];
};

interface RowAlignment {
  leftIndex?: number;
  rightIndex?: number;
  ambiguous?: boolean;
  moved?: boolean;
}

const rowsEqual = (
  left: Record<string, unknown>,
  right: Record<string, unknown>
) => tableRowSignature(left) === tableRowSignature(right);

const alignPureReorder = (
  leftRows: Record<string, unknown>[],
  rightRows: Record<string, unknown>[]
): RowAlignment[] | null => {
  if (leftRows.length !== rightRows.length || leftRows.length < 2) return null;
  const leftIndexByValue = new Map<string, number>();
  for (let index = 0; index < leftRows.length; index += 1) {
    const value = tableRowSignature(leftRows[index]);
    if (leftIndexByValue.has(value)) return null;
    leftIndexByValue.set(value, index);
  }
  const rightValues = rightRows.map(tableRowSignature);
  if (new Set(rightValues).size !== rightValues.length) return null;
  if (rightValues.some((value) => !leftIndexByValue.has(value))) return null;
  const alignments = rightValues.map((value, rightIndex) => ({
    leftIndex: leftIndexByValue.get(value),
    rightIndex,
    moved: leftIndexByValue.get(value) !== rightIndex,
  }));
  return alignments.some(({ leftIndex, rightIndex }) => leftIndex !== rightIndex)
    ? alignments
    : null;
};

const alignRowsByPosition = (
  leftRows: Record<string, unknown>[],
  rightRows: Record<string, unknown>[]
): RowAlignment[] => {
  const reordered = alignPureReorder(leftRows, rightRows);
  if (reordered) return reordered;

  if (leftRows.length === rightRows.length) {
    return leftRows.map((_, index) => ({
      leftIndex: index,
      rightIndex: index,
    }));
  }

  let prefixLength = 0;
  while (
    prefixLength < leftRows.length &&
    prefixLength < rightRows.length &&
    rowsEqual(leftRows[prefixLength], rightRows[prefixLength])
  ) {
    prefixLength += 1;
  }

  let suffixLength = 0;
  while (
    suffixLength < leftRows.length - prefixLength &&
    suffixLength < rightRows.length - prefixLength &&
    rowsEqual(
      leftRows[leftRows.length - suffixLength - 1],
      rightRows[rightRows.length - suffixLength - 1]
    )
  ) {
    suffixLength += 1;
  }

  const alignments: RowAlignment[] = Array.from(
    { length: prefixLength },
    (_, index) => ({ leftIndex: index, rightIndex: index })
  );
  const leftMiddleLength = leftRows.length - prefixLength - suffixLength;
  const rightMiddleLength = rightRows.length - prefixLength - suffixLength;
  const middleLength = Math.max(leftMiddleLength, rightMiddleLength);
  const ambiguous = leftMiddleLength > 1 && rightMiddleLength > 1;
  for (let offset = 0; offset < middleLength; offset += 1) {
    alignments.push({
      leftIndex:
        offset < leftMiddleLength ? prefixLength + offset : undefined,
      rightIndex:
        offset < rightMiddleLength ? prefixLength + offset : undefined,
      ambiguous,
    });
  }
  for (let offset = suffixLength; offset > 0; offset -= 1) {
    alignments.push({
      leftIndex: leftRows.length - offset,
      rightIndex: rightRows.length - offset,
    });
  }
  return alignments;
};

const buildPositionTableDiff = (
  beforeValue: unknown,
  afterValue: unknown,
  currentValue: unknown,
  columns: TableColumn[]
): TableFieldDiff | undefined => {
  const beforeRows = tableRowsOrEmpty(beforeValue);
  const afterRows = tableRowsOrEmpty(afterValue);
  const currentRows = tableRowsOrEmpty(currentValue);
  if (!beforeRows || !afterRows || !currentRows || !columns.length) return undefined;

  const beforeAfterAlignments = alignRowsByPosition(beforeRows, afterRows);
  const afterCurrentIndexMap = new Map<number, number>();
  const currentOnlyIndexes: number[] = [];
  alignRowsByPosition(afterRows, currentRows).forEach((alignment) => {
    if (
      alignment.leftIndex !== undefined &&
      alignment.rightIndex !== undefined
    ) {
      afterCurrentIndexMap.set(alignment.leftIndex, alignment.rightIndex);
    } else if (
      alignment.leftIndex === undefined &&
      alignment.rightIndex !== undefined
    ) {
      currentOnlyIndexes.push(alignment.rightIndex);
    }
  });
  const rows: TableRowDiff[] = [];
  let addedRows = 0;
  let removedRows = 0;
  let modifiedRows = 0;
  let changedCells = 0;

  beforeAfterAlignments.forEach((alignment, index) => {
    const beforeIndex = alignment.leftIndex;
    const afterIndex = alignment.rightIndex;
    const currentIndex =
      afterIndex === undefined
        ? undefined
        : afterCurrentIndexMap.get(afterIndex);
    const beforeRow =
      beforeIndex === undefined ? undefined : beforeRows[beforeIndex];
    const afterRow =
      afterIndex === undefined ? undefined : afterRows[afterIndex];
    const currentRow =
      currentIndex === undefined ? undefined : currentRows[currentIndex];
    const cells = columns.map((column): TableCellDiff => {
      const beforeRaw = beforeRow?.[column.column_id];
      const afterRaw = afterRow?.[column.column_id];
      const currentRaw = currentRow?.[column.column_id];
      const changed = !tableCellValuesEqual(beforeRaw, afterRaw);
      const currentDiff = !tableCellValuesEqual(afterRaw, currentRaw);
      if (changed) changedCells += 1;
      return {
        columnId: column.column_id,
        columnName: column.column_name || column.column_id,
        before: formatNestedValue(beforeRaw),
        after: formatNestedValue(afterRaw),
        current: formatNestedValue(currentRaw),
        changed,
        currentDiff,
      };
    });

    let status: TableRowDiffStatus = alignment.ambiguous
      ? 'ambiguous'
      : 'unchanged';
    if (!alignment.ambiguous && !beforeRow && afterRow) {
      status = 'added';
      addedRows += 1;
    } else if (!alignment.ambiguous && beforeRow && !afterRow) {
      status = 'removed';
      removedRows += 1;
    } else if (!alignment.ambiguous && cells.some((cell) => cell.changed)) {
      status = 'modified';
      modifiedRows += 1;
    } else if (
      !alignment.ambiguous &&
      alignment.moved
    ) {
      status = 'moved';
    }

    rows.push({
      key: `position:${index}`,
      beforeIndex,
      afterIndex,
      currentIndex,
      status,
      cells,
    });
  });

  currentOnlyIndexes.forEach((currentIndex) => {
    const currentRow = currentRows[currentIndex];
    rows.push({
      key: `current-only:${currentIndex}`,
      beforeIndex: undefined,
      afterIndex: undefined,
      currentIndex,
      status: 'unchanged',
      cells: columns.map((column) => ({
        columnId: column.column_id,
        columnName: column.column_name || column.column_id,
        before: '--',
        after: '--',
        current: formatNestedValue(currentRow[column.column_id]),
        changed: false,
        currentDiff: true,
      })),
    });
  });

  return {
    matchMode: rows.some((row) => row.status === 'ambiguous')
      ? 'row-level'
      : 'position',
    fallbackReason: rows.some((row) => row.status === 'ambiguous')
      ? 'ambiguous-rows'
      : undefined,
    rows,
    summary: { addedRows, removedRows, modifiedRows, changedCells },
  };
};

interface IndexedTableRows {
  rows: Map<string, { index: number; row: Record<string, unknown> }>;
  reason?: 'missing-row-key' | 'duplicate-row-key';
}

const normalizeRowKey = (
  value: unknown,
  column: TableColumn
): string | null => {
  if (value === undefined || value === null || value === '') return null;
  if (column.column_type === 'number') {
    const numberValue = Number(value);
    return Number.isFinite(numberValue) ? `number:${numberValue}` : null;
  }
  const stringValue = String(value).trim();
  return stringValue ? `string:${stringValue}` : null;
};

const indexTableRows = (
  rows: Record<string, unknown>[],
  rowKeyColumn: TableColumn
): IndexedTableRows => {
  const indexed = new Map<
    string,
    { index: number; row: Record<string, unknown> }
  >();
  for (let index = 0; index < rows.length; index += 1) {
    const key = normalizeRowKey(rows[index][rowKeyColumn.column_id], rowKeyColumn);
    if (key === null) return { rows: indexed, reason: 'missing-row-key' };
    if (indexed.has(key)) {
      return { rows: indexed, reason: 'duplicate-row-key' };
    }
    indexed.set(key, { index, row: rows[index] });
  }
  return { rows: indexed };
};

const buildRowKeyTableDiff = (
  beforeValue: unknown,
  afterValue: unknown,
  currentValue: unknown,
  columns: TableColumn[],
  rowKeyColumn: TableColumn
): TableFieldDiff | undefined => {
  const beforeRows = tableRowsOrEmpty(beforeValue);
  const afterRows = tableRowsOrEmpty(afterValue);
  const currentRows = tableRowsOrEmpty(currentValue);
  if (!beforeRows || !afterRows || !currentRows) return undefined;

  const beforeIndex = indexTableRows(beforeRows, rowKeyColumn);
  const afterIndex = indexTableRows(afterRows, rowKeyColumn);
  const currentIndex = indexTableRows(currentRows, rowKeyColumn);
  const fallbackReason =
    beforeIndex.reason || afterIndex.reason || currentIndex.reason;
  if (fallbackReason) {
    const fallback = buildPositionTableDiff(
      beforeValue,
      afterValue,
      currentValue,
      columns
    );
    return fallback ? { ...fallback, fallbackReason } : undefined;
  }

  const orderedKeys = Array.from(
    new Set([
      ...afterIndex.rows.keys(),
      ...beforeIndex.rows.keys(),
      ...currentIndex.rows.keys(),
    ])
  );
  let addedRows = 0;
  let removedRows = 0;
  let modifiedRows = 0;
  let changedCells = 0;
  const rows = orderedKeys.map((key): TableRowDiff => {
    const beforeEntry = beforeIndex.rows.get(key);
    const afterEntry = afterIndex.rows.get(key);
    const currentEntry = currentIndex.rows.get(key);
    const cells = columns.map((column): TableCellDiff => {
      const beforeRaw = beforeEntry?.row[column.column_id];
      const afterRaw = afterEntry?.row[column.column_id];
      const currentRaw = currentEntry?.row[column.column_id];
      const changed = !tableCellValuesEqual(beforeRaw, afterRaw);
      const currentDiff = !tableCellValuesEqual(afterRaw, currentRaw);
      if (changed) changedCells += 1;
      return {
        columnId: column.column_id,
        columnName: column.column_name || column.column_id,
        before: formatNestedValue(beforeRaw),
        after: formatNestedValue(afterRaw),
        current: formatNestedValue(currentRaw),
        changed,
        currentDiff,
      };
    });

    let status: TableRowDiffStatus = 'unchanged';
    if (!beforeEntry && afterEntry) {
      status = 'added';
      addedRows += 1;
    } else if (beforeEntry && !afterEntry) {
      status = 'removed';
      removedRows += 1;
    } else if (cells.some((cell) => cell.changed)) {
      status = 'modified';
      modifiedRows += 1;
    } else if (beforeEntry?.index !== afterEntry?.index) {
      status = 'moved';
    }

    return {
      key: `row-key:${key}`,
      beforeIndex: beforeEntry?.index,
      afterIndex: afterEntry?.index,
      currentIndex: currentEntry?.index,
      status,
      cells,
    };
  });

  return {
    matchMode: 'row-key',
    rowKeyColumnId: rowKeyColumn.column_id,
    rows,
    summary: { addedRows, removedRows, modifiedRows, changedCells },
  };
};

export const buildTableDiff = (
  beforeValue: unknown,
  afterValue: unknown,
  currentValue: unknown,
  columns: TableColumn[]
): TableFieldDiff | undefined => {
  const rowKeyColumn = columns.find((column) => column.is_row_key === true);
  return rowKeyColumn
    ? buildRowKeyTableDiff(
      beforeValue,
      afterValue,
      currentValue,
      columns,
      rowKeyColumn
    )
    : buildPositionTableDiff(beforeValue, afterValue, currentValue, columns);
};
