import React, { useEffect, useRef, useState } from 'react';
import { CopyTwoTone } from '@ant-design/icons';
import type { TableDataItem } from '@/components/log-analysis-widgets/types';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useCopy } from '@/hooks/useCopy';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';

export interface LogAnalysisMessageTableProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const LogAnalysisMessageTable: React.FC<LogAnalysisMessageTableProps> = ({
  rawData,
  loading = false,
  config,
}) => {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [scrollY, setScrollY] = useState<number>(300);
  const [expandedRowKeys, setExpandedRowKeys] = useState<React.Key[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loading) {
      const data = (rawData || []).map((item: TableDataItem, index: number) => ({
        id: index,
        ...item,
      }));
      setTableData(data);
    }
  }, [loading, rawData]);

  useEffect(() => {
    const updateScrollHeight = () => {
      if (containerRef.current) {
        const containerHeight = containerRef.current.clientHeight;
        const calculatedHeight = Math.max(20, containerHeight - 80);
        setScrollY(calculatedHeight);
      }
    };

    updateScrollHeight();

    const resizeObserver = new ResizeObserver(() => {
      updateScrollHeight();
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  const getRowExpandRender = (record: TableDataItem) => {
    return (
      <div className="w-full pl-9">
        <div className="border-b border-[var(--color-border-1)] pb-2.5">
          <div className="mb-1">
            <CopyTwoTone className="mr-[4px] cursor-pointer" onClick={() => copy(record._msg)} />
            <span className="break-all font-[500]">{record._msg}</span>
          </div>
          <div>
            <span className="mr-3">
              <span className="text-[var(--color-text-3)]">{t('common.time')}：</span>
              <span>{convertToLocalizedTime(record._time, 'YYYY-MM-DD HH:mm:ss.SSS')}</span>
            </span>
            <span className="mr-3">
              <span className="text-[var(--color-text-3)]">{t('log.integration.collector')}：</span>
              <span>{record.collector || '--'}</span>
            </span>
            <span>
              <span className="text-[var(--color-text-3)]">{t('log.integration.collectType')}：</span>
              <span>{record.collect_type || '--'}</span>
            </span>
          </div>
        </div>
        <ul>
          {Object.entries(record)
            .map(([key, value]) => ({
              label: key,
              value,
            }))
            .filter((item) => item.label !== 'id')
            .map((item: TableDataItem, index: number) => (
              <li className="mt-[10px] flex items-start" key={index}>
                <div className="mr-[10px] flex w-[20%] min-w-[100px] items-center">
                  <div className="flex max-w-[100%] cursor-pointer">
                    <EllipsisWithTooltip
                      text={item.label}
                      className="w-full overflow-hidden text-ellipsis whitespace-nowrap text-[var(--color-text-3)]"
                    />
                    <span className="text-[var(--color-text-3)]">:</span>
                  </div>
                </div>
                <span className="cursor-pointer">
                  <span className="break-all">{item.value}</span>
                </span>
              </li>
            ))}
        </ul>
      </div>
    );
  };

  return (
    <div ref={containerRef} className="flex h-full">
      <CustomTable
        className="w-full"
        columns={config?.columns || []}
        dataSource={tableData}
        loading={loading}
        scroll={{ y: scrollY }}
        virtual
        rowKey="id"
        expandable={{
          columnWidth: 36,
          expandedRowRender: (record) => getRowExpandRender(record),
          expandedRowKeys,
          onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as React.Key[]),
        }}
      />
    </div>
  );
};

export default LogAnalysisMessageTable;
