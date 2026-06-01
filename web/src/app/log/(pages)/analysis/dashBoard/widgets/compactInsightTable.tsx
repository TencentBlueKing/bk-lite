import React, { useMemo } from 'react';
import { Empty, Spin } from 'antd';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

interface CompactInsightTableProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const toNumber = (value: unknown) => {
  const parsed = Number.parseFloat(String(value ?? 0).replace(/,/g, ''));
  return Number.isNaN(parsed) ? 0 : parsed;
};

const formatCellValue = (value: unknown) => {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'number') return value.toLocaleString();
  return String(value);
};

const CompactInsightTable: React.FC<CompactInsightTableProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const rows = useMemo(() => (Array.isArray(rawData) ? rawData : []), [rawData]);
  const columns = config?.columns || [];
  const showIndex = config?.showIndex !== false;
  const metricBarField = config?.metricBarField;

  const maxMetricValue = useMemo(() => {
    if (!metricBarField) return 0;
    return rows.reduce(
      (max: number, row: Record<string, unknown>) =>
        Math.max(max, toNumber(row?.[metricBarField])),
      0
    );
  }, [metricBarField, rows]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!rows.length || !columns.length) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  const minWidth = columns.reduce(
    (sum: number, column: Record<string, unknown>) =>
      sum + Number(column.width || 120),
    showIndex ? 56 : 0
  );

  return (
    <div className="h-full overflow-auto">
      <table
        className="w-full table-fixed border-separate border-spacing-0 text-xs"
        style={{ minWidth }}
      >
        <thead className="sticky top-0 z-10">
          <tr>
            {showIndex && (
              <th className="border-b border-[var(--color-border-2)] bg-[var(--color-fill-2)] px-3 py-2 text-center font-medium text-[var(--color-text-3)]">
                #
              </th>
            )}
            {columns.map((column: Record<string, unknown>) => (
              <th
                key={String(column.key || column.dataIndex)}
                className="border-b border-[var(--color-border-2)] bg-[var(--color-fill-2)] px-3 py-2 text-left font-medium text-[var(--color-text-3)]"
                style={{ width: Number(column.width || 120) }}
              >
                {String(column.title || '')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row: Record<string, unknown>, index: number) => (
            <tr
              key={String(row.id || row.time || row.message || row.component || index)}
              className={index % 2 === 0 ? 'bg-white' : 'bg-[var(--color-fill-1)]'}
            >
              {showIndex && (
                <td className="border-b border-[var(--color-border-2)] px-3 py-2 align-top">
                  <span className="inline-flex min-w-[24px] items-center justify-center rounded-full bg-[var(--color-fill-3)] px-2 py-0.5 text-[11px] font-semibold text-[var(--color-text-2)]">
                    {index + 1}
                  </span>
                </td>
              )}
              {columns.map((column: Record<string, unknown>) => {
                const dataIndex = String(column.dataIndex || '');
                const rawValue = row?.[dataIndex];
                const isMetricBar = metricBarField === dataIndex;
                const metricValue = isMetricBar ? toNumber(rawValue) : 0;
                const metricPercent =
                  isMetricBar && maxMetricValue > 0
                    ? Math.max(6, (metricValue / maxMetricValue) * 100)
                    : 0;

                return (
                  <td
                    key={String(column.key || dataIndex)}
                    className="border-b border-[var(--color-border-2)] px-3 py-2 align-top text-[var(--color-text-2)]"
                  >
                    {isMetricBar ? (
                      <div className="flex min-w-0 flex-col gap-1">
                        <span className="font-medium text-[var(--color-text-1)]">
                          {formatCellValue(rawValue)}
                        </span>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-fill-3)]">
                          <div
                            className="h-full rounded-full bg-[#f5222d]"
                            style={{ width: `${metricPercent}%` }}
                          />
                        </div>
                      </div>
                    ) : typeof rawValue === 'string' ? (
                      <EllipsisWithTooltip
                        text={formatCellValue(rawValue)}
                        className="block w-full truncate leading-5"
                      />
                    ) : (
                      <span className="leading-5">{formatCellValue(rawValue)}</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default CompactInsightTable;
