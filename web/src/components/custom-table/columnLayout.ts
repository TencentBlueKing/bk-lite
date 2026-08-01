export const DEFAULT_COL_WIDTH = 150;

type ColumnWidth = number | string | undefined;

interface ColumnLike {
  dataIndex?: string | number | readonly (string | number)[];
  key?: string | number;
  width?: ColumnWidth;
}

interface ResolveColumnLayoutOptions {
  autoScrollX: boolean;
  columns: ColumnLike[];
  columnWidths: Record<string, number>;
  tableLayout?: 'auto' | 'fixed';
}

export const getColumnKey = (column: ColumnLike, index: number): string => {
  if (column.key !== undefined) return String(column.key);
  if (Array.isArray(column.dataIndex)) return column.dataIndex.join('.');
  if (column.dataIndex !== undefined) return String(column.dataIndex);
  return `col-${index}`;
};

export const resolveColumnLayout = ({
  autoScrollX,
  columns,
  columnWidths,
  tableLayout,
}: ResolveColumnLayoutOptions) => {
  const widths = columns.map((column, index) => {
    const columnKey = getColumnKey(column, index);
    return columnWidths[columnKey] || column.width || DEFAULT_COL_WIDTH;
  });

  return {
    widths,
    scrollX: autoScrollX
      ? widths.reduce<number>((total, width) => (
        total + (typeof width === 'number' ? width : DEFAULT_COL_WIDTH)
      ), 0)
      : undefined,
    tableLayout,
  };
};
