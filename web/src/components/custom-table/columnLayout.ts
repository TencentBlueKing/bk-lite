export const DEFAULT_COL_WIDTH = 150;
export const DEFAULT_SELECTION_COLUMN_WIDTH = 32;

export const resolveSelectionColumnWidth = (
  columnWidth?: number | string,
): number => {
  if (typeof columnWidth === 'number' && Number.isFinite(columnWidth) && columnWidth > 0) {
    return columnWidth;
  }
  if (typeof columnWidth === 'string' && columnWidth.endsWith('px')) {
    const parsed = Number.parseFloat(columnWidth);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_SELECTION_COLUMN_WIDTH;
  }
  return DEFAULT_SELECTION_COLUMN_WIDTH;
};

type ColumnWidth = number | string | undefined;

interface ColumnLike {
  dataIndex?: string | number | readonly (string | number)[];
  key?: string | number;
  width?: ColumnWidth;
  fixed?: boolean | 'left' | 'right';
}

interface ResolveColumnLayoutOptions {
  autoScrollX: boolean;
  columns: ColumnLike[];
  columnWidths: Record<string, number>;
  tableLayout?: 'auto' | 'fixed';
  containerWidth?: number;
  /** 勾选列等不在 columns 里的固定槽，铺满时要从容器宽度里扣掉 */
  reservedWidth?: number;
}

export const getColumnKey = (column: ColumnLike, index: number): string => {
  if (column.key !== undefined) return String(column.key);
  if (Array.isArray(column.dataIndex)) return column.dataIndex.join('.');
  if (column.dataIndex !== undefined) return String(column.dataIndex);
  return `col-${index}`;
};

const toPixelWidth = (width: ColumnWidth): number => {
  if (typeof width === 'number') return width;
  if (typeof width === 'string' && width.endsWith('px')) {
    const parsed = Number.parseFloat(width);
    return Number.isFinite(parsed) ? parsed : DEFAULT_COL_WIDTH;
  }
  return DEFAULT_COL_WIDTH;
};

export const estimateContentMinWidth = (
  columns: ColumnLike[],
  columnWidths: Record<string, number> = {},
): number =>
  columns.reduce((total, column, index) => {
    const columnKey = getColumnKey(column, index);
    if (columnWidths[columnKey]) return total + columnWidths[columnKey];
    return total + toPixelWidth(column.width);
  }, 0);

export const scaleWidthsToContainer = (
  widths: number[],
  containerWidth: number,
  locked: boolean[] = [],
): number[] => {
  const total = widths.reduce((sum, width) => sum + width, 0);
  if (total <= 0 || containerWidth <= 0) return widths;

  const flexibleIndexes = widths
    .map((_, index) => index)
    .filter((index) => !locked[index]);
  const scaleSource = flexibleIndexes.length > 0 ? flexibleIndexes : widths.map((_, index) => index);
  const lockedTotal = flexibleIndexes.length > 0
    ? widths.reduce((sum, width, index) => sum + (locked[index] ? width : 0), 0)
    : 0;
  const flexibleTotal = scaleSource.reduce((sum, index) => sum + widths[index], 0);
  const flexibleBudget = Math.max(scaleSource.length, containerWidth - lockedTotal);
  if (flexibleTotal <= 0) return widths;

  const scale = flexibleBudget / flexibleTotal;
  let usedFlexible = 0;
  return widths.map((width, index) => {
    if (!scaleSource.includes(index)) return width;
    if (index === scaleSource[scaleSource.length - 1]) {
      return Math.max(1, flexibleBudget - usedFlexible);
    }
    const next = Math.max(1, Math.round(width * scale));
    usedFlexible += next;
    return next;
  });
};

export const resolveColumnLayout = ({
  autoScrollX,
  columns,
  columnWidths,
  tableLayout,
  containerWidth,
  reservedWidth = 0,
}: ResolveColumnLayoutOptions) => {
  const contentMinWidth = estimateContentMinWidth(columns, columnWidths);
  const gutter = Math.max(0, reservedWidth);
  const measuredWidth =
    typeof containerWidth === 'number' && containerWidth > 0
      ? containerWidth
      : undefined;
  const usableWidth =
    measuredWidth !== undefined
      ? Math.max(0, measuredWidth - gutter)
      : undefined;
  const overflows =
    autoScrollX
    && usableWidth !== undefined
    && contentMinWidth > usableWidth;

  const minWidths = columns.map((column, index) => {
    const columnKey = getColumnKey(column, index);
    if (columnWidths[columnKey]) return columnWidths[columnKey];
    if (typeof column.width === 'number') return column.width;
    if (typeof column.width === 'string' && column.width.endsWith('px')) {
      return toPixelWidth(column.width);
    }
    return DEFAULT_COL_WIDTH;
  });

  if (overflows) {
    return {
      widths: minWidths,
      scrollX: contentMinWidth + gutter,
      tableLayout: tableLayout ?? 'fixed',
    };
  }

  if (usableWidth !== undefined && contentMinWidth > 0 && contentMinWidth <= usableWidth) {
    return {
      widths: contentMinWidth < usableWidth
        ? scaleWidthsToContainer(
          minWidths,
          usableWidth,
          columns.map((column) => Boolean(column.fixed)),
        )
        : minWidths,
      scrollX: undefined,
      tableLayout: tableLayout ?? 'fixed',
    };
  }

  return {
    widths: columns.map((column, index) => {
      const columnKey = getColumnKey(column, index);
      if (columnWidths[columnKey]) return columnWidths[columnKey];
      if (column.width !== undefined) return column.width;
      return undefined;
    }),
    scrollX: undefined,
    tableLayout: tableLayout ?? 'auto',
  };
};
