'use client';
import React, { useState, useRef, useMemo, useCallback } from 'react';
import { Table, TableProps } from 'antd';
import { ColumnType } from 'antd/es/table';
import './index.scss';

interface ResizableTitleProps extends React.HTMLAttributes<HTMLTableCellElement> {
  onResize?: (width: number) => void;
  width?: number;
}

const ResizableTitle: React.FC<ResizableTitleProps> = (props) => {
  const { onResize, width, children, ...restProps } = props;
  const thRef = useRef<HTMLTableCellElement>(null);
  const startXRef = useRef<number>(0);
  const startWidthRef = useRef<number>(0);

  if (!width || !onResize) {
    return <th {...restProps}>{children}</th>;
  }

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    startXRef.current = e.clientX;
    startWidthRef.current = thRef.current?.offsetWidth || width;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startXRef.current;
      const newWidth = Math.max(60, startWidthRef.current + delta);
      onResize(newWidth);
    };

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  return (
    <th
      ref={thRef}
      {...restProps}
      style={{
        ...restProps.style,
        width,
        minWidth: 60,
        maxWidth: width,
        userSelect: 'none',
        position: 'relative',
      }}
    >
      {children}
      <span
        className="resize-handle"
        onMouseDown={handleMouseDown}
        onClick={(e) => e.stopPropagation()}
      />
    </th>
  );
};

type ColumnWidths = Record<string, number>;

interface UseResizableColumnsOptions<T> {
  columns: ColumnType<T>[];
  defaultWidths?: ColumnWidths;
}

export function useResizableColumns<T>({ columns, defaultWidths }: UseResizableColumnsOptions<T>) {
  const initialWidths = useMemo(() => {
    const widths: ColumnWidths = { ...defaultWidths };
    columns.forEach((col) => {
      const key = (col.dataIndex || col.key) as string;
      if (key && !widths[key] && col.width) {
        widths[key] = col.width as number;
      }
    });
    return widths;
  }, []);

  const [columnWidths, setColumnWidths] = useState<ColumnWidths>(initialWidths);

  const handleResize = useCallback(
    (key: string) => (width: number) => {
      setColumnWidths((prev) => ({ ...prev, [key]: width }));
    },
    []
  );

  const resizableColumns = useMemo(() => {
    return columns.map((col) => {
      const key = (col.dataIndex || col.key) as string;
      const width = columnWidths[key] || (col.width as number);
      return {
        ...col,
        width,
        onHeaderCell: () => ({
          width,
          onResize: handleResize(key),
        }),
      };
    });
  }, [columns, columnWidths, handleResize]);

  const tableScrollX = useMemo(() => {
    return Object.values(columnWidths).reduce((sum, w) => sum + w, 0);
  }, [columnWidths]);

  const tableComponents = useMemo(
    () => ({
      header: {
        cell: ResizableTitle,
      },
    }),
    []
  );

  return {
    columns: resizableColumns,
    components: tableComponents,
    scrollX: tableScrollX,
    columnWidths,
    setColumnWidths,
  };
}

interface ResizableTableProps<T> extends Omit<TableProps<T>, 'columns'> {
  columns: ColumnType<T>[];
  defaultColumnWidths?: ColumnWidths;
}

function ResizableTable<T extends object>({
  columns: inputColumns,
  defaultColumnWidths,
  scroll,
  ...rest
}: ResizableTableProps<T>) {
  const { columns, components, scrollX } = useResizableColumns({
    columns: inputColumns,
    defaultWidths: defaultColumnWidths,
  });

  return (
    <Table<T>
      {...rest}
      columns={columns}
      components={components}
      scroll={{ ...scroll, x: scrollX }}
    />
  );
}

export default ResizableTable;
