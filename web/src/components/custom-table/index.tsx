import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Table, TableProps, Pagination } from 'antd';
import { SettingFilled, HolderOutlined } from '@ant-design/icons';
import customTableStyle from './index.module.scss';
import FieldSettingModal from './fieldSettingModal';
import { ColumnItem, GroupFieldItem } from '@/types/index';
import { TableCurrentDataSource, FilterValue, SorterResult } from 'antd/es/table/interface';
import { cloneDeep } from 'lodash';
import EllipsisWithTooltip from '../ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import ResizableTitle from './resizableTitle';

interface CustomTableProps<T>
  extends Omit<TableProps<T>, 'bordered' | 'fieldSetting' | 'onSelectFields'> {
  bordered?: boolean;
  size?: 'small' | 'middle' | 'large';
  fieldSetting?: {
    showSetting: boolean;
    displayFieldKeys: string[];
    choosableFields: ColumnItem[];
    groupFields?: GroupFieldItem[];
  };
  onSelectFields?: (fields: string[]) => void;
  rowDraggable?: boolean;
  onRowDragStart?: (index: number) => void;
  onRowDragEnd?: (
    targetTableData: TableProps<T>['dataSource'],
    sourceIndex: number,
    targetIndex: number
  ) => void;
}

interface FieldRef {
  showModal: () => void;
}

const CustomTable = <T extends object>({
  bordered = false,
  size = "middle",
  fieldSetting = {
    showSetting: false,
    displayFieldKeys: [],
    choosableFields: [],
  },
  onSelectFields = () => [],
  loading,
  scroll,
  pagination,
  onChange,
  rowDraggable = false,
  onRowDragStart,
  onRowDragEnd,
  rowSelection,
  ...TableProps
}: CustomTableProps<T>) => {
  const { t } = useTranslation();
  const fieldRef = useRef<FieldRef>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerHeight, setContainerHeight] = useState<number | undefined>(undefined);
  const [tableHeight, setTableHeight] = useState<number | undefined>(undefined);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [filters, setFilters] = useState<Record<string, FilterValue | null>>({});
  const [sorter, setSorter] = useState<SorterResult<T> | SorterResult<T>[]>({});
  const [extra, setExtra] = useState<TableCurrentDataSource<T>>();
  const [columns, setColumns] = useState<any[]>([]);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({});

  // 监听父容器高度变化
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const updateTableHeight = () => {
      const parentElement = container.parentElement;
      if (!parentElement) return;

      // 如果已经设置了 scroll.y，优先使用设置的值
      if (scroll?.y) {
        const parsedHeight = parseCalcY(scroll.y as string);
        setTableHeight(parsedHeight);
        // 容器高度 = 表格滚动高度 + 表头高度 + 分页高度
        const TABLE_HEADER_HEIGHT = size === 'small' ? 47 : size === 'middle' ? 55 : 63;
        const PAGINATION_HEIGHT = pagination ? 56 : 0;
        setContainerHeight(parsedHeight + TABLE_HEADER_HEIGHT + PAGINATION_HEIGHT);
        return;
      }

      // 否则根据父容器高度自动计算
      if (pagination) {
        const parentHeight = parentElement.clientHeight;
        const TABLE_HEADER_HEIGHT =
          size === 'small' ? 47 : size === 'middle' ? 55 : 63;
        const PAGINATION_HEIGHT = pagination ? 56 : 0;
        const calculatedHeight =
          parentHeight - TABLE_HEADER_HEIGHT - PAGINATION_HEIGHT;
        setTableHeight(calculatedHeight > 0 ? calculatedHeight : undefined);
        setContainerHeight(parentHeight);
      }
    };

    updateTableHeight();

    const resizeObserver = new ResizeObserver(() => {
      updateTableHeight();
    });

    if (container.parentElement) {
      resizeObserver.observe(container.parentElement);
    }

    // 监听窗口大小变化
    window.addEventListener('resize', updateTableHeight);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', updateTableHeight);
    };
  }, [scroll, pagination, size]);

  useEffect(() => {
    const initialColumns = renderColumns();
    setColumns(initialColumns);
  }, [TableProps.columns, rowDraggable]);

  const enhanceColumnRender = (column: any) => {
    if (column.render) return column;

    return {
      ...column,
      render: (text: any) => {
        if ([null, undefined, ''].includes(text)) return '--';
        if (typeof text === 'string') {
          return (
            <EllipsisWithTooltip
              text={text}
              className="truncate w-full"
            />
          );
        }
        return text;
      }
    };
  };

  const renderColumns = useCallback(() => {
    let cols = TableProps.columns || [];

    cols = cols.map(col => enhanceColumnRender(col));

    if (rowDraggable) {
      return [
        {
          key: 'sort',
          align: 'center',
          width: 30,
          title: '',
          dataIndex: 'sort',
          render: () => (
            <HolderOutlined className="font-[800] text-[16px] mr-[6px] cursor-move" />
          ),
        },
        ...cols,
      ];
    }
    return cols;
  }, [TableProps.columns, rowDraggable]);

  // 获取列的唯一标识
  const getColumnKey = (col: any, index: number): string => {
    return col.key || col.dataIndex || `col-${index}`;
  };

  // 处理列宽拖拽
  const handleColumnResize = (colKey: string) => (newWidth: number) => {
    setColumnWidths(prev => ({
      ...prev,
      [colKey]: newWidth,
    }));
  };

  // 将列宽状态和 onHeaderCell 合并到 columns
  const DEFAULT_COL_WIDTH = 150;

  const resizableColumns = useCallback(() => {
    return columns.map((col: any, index: number) => {
      const colKey = getColumnKey(col, index);
      const width = columnWidths[colKey] || col.width || DEFAULT_COL_WIDTH;

      return {
        ...col,
        width,
        onHeaderCell: () => ({
          width,
          resizeHandler: handleColumnResize(colKey),
        }),
      };
    });
  }, [columns, columnWidths]);

  // 计算 scroll.x：列宽总和，当超过容器宽度时产生横向滚动
  const getScrollX = useCallback(() => {
    const cols = resizableColumns();
    return cols.reduce((sum: number, col: any) => sum + (col.width || DEFAULT_COL_WIDTH), 0);
  }, [resizableColumns]);

  const parseCalcY = (value: string): number => {
    const vh = window.innerHeight;
    let total = 0;

    // Regex to parse expressions and capture operators, numbers, and units
    const calcRegex = /([-+]?)\s*(\d*\.?\d+)(vh|px)/g;
    let match: RegExpExecArray | null;

    while ((match = calcRegex.exec(value)) !== null) {
      const sign = match[1] || '+';
      const numValue = parseFloat(match[2]);
      const unit = match[3];

      let result = 0;
      if (unit === 'vh') {
        result = (numValue / 100) * vh;
      } else if (unit === 'px') {
        result = numValue;
      }

      if (sign === '-') {
        total -= result;
      } else {
        total += result;
      }
    }

    return total;
  };

  const showFieldSetting = () => {
    fieldRef.current?.showModal();
  };

  const handlePageChange = (current: number, pageSize: number) => {
    if (pagination && pagination.onChange) {
      pagination.onChange(current, pageSize);
    }
    onChange &&
      onChange(
        { current, pageSize },
        filters,
        sorter,
        extra as TableCurrentDataSource<T>
      );
  };

  const handleDragStart = (index: number) => () => {
    setDraggedIndex(index);
    onRowDragStart?.(index);
  };

  const handleDragOver =
    (index: number) => (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setHoveredIndex(index);
    };

  const handleDrop =
    (index: number) => (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const sourceIndex = draggedIndex;
      const targetIndex = index;
      setDraggedIndex(null);
      setHoveredIndex(null);

      if (sourceIndex === null) {
        const targetTableData = cloneDeep(TableProps.dataSource) as T[];
        onRowDragEnd?.(targetTableData, targetIndex, -1);
        return;
      }

      if (
        sourceIndex !== null &&
        targetIndex !== null &&
        sourceIndex !== targetIndex
      ) {
        const targetTableData = cloneDeep(TableProps.dataSource) as T[];
        const [movedItem] = targetTableData.splice(sourceIndex, 1);
        targetTableData.splice(targetIndex, 0, movedItem);
        onRowDragEnd?.(targetTableData, targetIndex, sourceIndex);
      }
    };

  const renderRow = (index: number) => {
    return {
      index,
      draggable: rowDraggable,
      onDragStart: handleDragStart(index),
      onDragOver: handleDragOver(index),
      onDrop: handleDrop(index),
    };
  };

  const handleTableChange = (
    filters: Record<string, FilterValue | null>,
    sorter: SorterResult<T> | SorterResult<T>[],
    extra: TableCurrentDataSource<T>
  ) => {
    setFilters(filters);
    setSorter(sorter);
    setExtra(extra);
    onChange &&
      onChange(
        {
          total: pagination ? pagination.total : 0,
          current: pagination ? pagination.current : 1,
          pageSize: pagination ? pagination.pageSize : 20,
        },
        filters,
        sorter,
        extra
      );
  };

  // 合并外部传入的 components 和列宽拖拽的 header cell
  const mergedComponents = {
    ...TableProps.components,
    header: {
      ...TableProps.components?.header,
      cell: ResizableTitle,
    },
  };

  return (
    <div
      ref={containerRef}
      className={`relative ${customTableStyle.customTable}`}
      style={{
        height: containerHeight && pagination ? `${containerHeight}px` : 'auto',
      }}
    >
      <Table
        size={size}
        bordered={bordered}
        scroll={{ x: getScrollX(), ...(tableHeight ? { ...scroll, y: tableHeight } : scroll) }}
        loading={loading}
        pagination={false}
        rowClassName={(record, index) =>
          hoveredIndex === index ? 'bg-[var(--ant-table-row-hover-bg)]' : ''
        }
        onRow={(record, index) => renderRow(index!)}
        {...TableProps}
        columns={resizableColumns()}
        components={mergedComponents}
        rowSelection={rowSelection}
        onChange={(pageConfig, filters, sorter, extra) =>
          handleTableChange(filters, sorter, extra)
        }
      />
      {pagination && !loading && !!pagination.total && (<div className="absolute right-0 bottom-0 flex justify-end">
        <Pagination
          total={pagination?.total}
          showSizeChanger
          current={pagination?.current}
          pageSize={pagination?.pageSize}
          onChange={handlePageChange}
          showTotal={(total) => (
            <div className="flex items-center">
              <span>{`${t('common.total')} ${total} ${t('common.items')}`}</span>
              {rowSelection ? (
                <div className="text-sm h-[32px] flex items-center px-4">
                  {`${t('common.checked')} ${rowSelection?.selectedRowKeys?.length} ${t('common.items')}`}
                </div>
              ) : null}
            </div>
          )}
        />
      </div>)}
      {fieldSetting.showSetting ? (
        <SettingFilled
          style={{ top: size === 'small' ? 12 : size === 'middle' ? 16 : 20 }}
          className={customTableStyle.setting}
          onClick={showFieldSetting}
        />
      ) : null}
      <FieldSettingModal
        ref={fieldRef}
        choosableFields={fieldSetting.choosableFields || []}
        displayFieldKeys={fieldSetting.displayFieldKeys}
        groupFields={fieldSetting.groupFields}
        onConfirm={onSelectFields}
      />
    </div>
  );
};

export default CustomTable;
