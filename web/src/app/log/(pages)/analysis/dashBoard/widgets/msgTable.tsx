import React, { useEffect, useState, useRef } from 'react';
import CustomTable from '@/components/custom-table';
import { TableDataItem } from '@/app/log/types';
import { CopyTwoTone } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useCopy } from '@/hooks/useCopy';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

interface MsgtableProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const Msgtable: React.FC<MsgtableProps> = ({
  rawData,
  loading = false,
  config,
}) => {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [scrollY, setScrollY] = useState<number>(300);
  const containerRef = useRef<HTMLDivElement>(null);
  const [expandedRowKeys, setExpandedRowKeys] = useState<React.Key[]>([]);

  useEffect(() => {
    if (!loading) {
      const data = (rawData || []).map((item: TableDataItem, index: number) => {
        return {
          id: index,
          ...item,
        };
      });
      setTableData(data);
    }
  }, [rawData, loading]);

  useEffect(() => {
    const updateScrollHeight = () => {
      if (containerRef.current) {
        const containerHeight = containerRef.current.clientHeight;
        // 减去表格头部高度 (大约 55px) 和一些边距
        const calculatedHeight = Math.max(20, containerHeight - 80);
        setScrollY(calculatedHeight);
      }
    };
    updateScrollHeight();
    // 监听窗口大小变化
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
        <div className="pb-2.5 border-b border-[var(--color-border-1)]">
          <div className="mb-1">
            <CopyTwoTone
              className="cursor-pointer mr-[4px]"
              onClick={() => copy(record._msg)}
            />
            <span className="font-[500] break-all">{record._msg}</span>
          </div>
          <div>
            <span className="mr-3">
              <span className="text-[var(--color-text-3)]">
                {t('common.time')}：
              </span>
              <span>
                {convertToLocalizedTime(
                  record._time,
                  'YYYY-MM-DD HH:mm:ss.SSS'
                )}
              </span>
            </span>
            <span className="mr-3">
              <span className="text-[var(--color-text-3)]">
                {t('log.integration.collector')}：
              </span>
              <span>{record.collector || '--'}</span>
            </span>
            <span>
              <span className="text-[var(--color-text-3)]">
                {t('log.integration.collectType')}：
              </span>
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
              <li className="flex items-start mt-[10px]" key={index}>
                <div className="flex items-center min-w-[100px] w-[20%] mr-[10px]">
                  <div className="flex max-w-[100%] cursor-pointer">
                    <EllipsisWithTooltip
                      text={item.label}
                      className="w-full overflow-hidden text-[var(--color-text-3)] text-ellipsis whitespace-nowrap"
                    ></EllipsisWithTooltip>
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
    <div ref={containerRef} className="h-full flex">
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
          expandedRowKeys: expandedRowKeys,
          onExpandedRowsChange: (keys) =>
            setExpandedRowKeys(keys as React.Key[]),
        }}
      />
    </div>
  );
};

export default Msgtable;
